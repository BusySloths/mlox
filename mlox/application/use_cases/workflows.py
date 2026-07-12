from __future__ import annotations

from typing import Any

from mlox.application.result import OperationResult
from mlox.config import load_service_config_by_id
from mlox.secret_manager import (
    SECRET_MANAGER_KEYFILE_ENV,
    SECRET_MANAGER_KEYFILE_PW_ENV,
    get_encrypted_access_keyfile,
)
from mlox.service import ServiceCapability
from mlox.utils import generate_pw


GITHUB_REPOSITORY_TEMPLATE_ID = "github-repo-0.1-beta-docker"


def describe_workflows(infra) -> OperationResult:
    """Return workflow orchestrators and their DAG/workflow metadata."""

    if infra is None:
        return OperationResult(False, 80, "Infrastructure is unavailable.")

    orchestrators: list[dict[str, Any]] = []
    workflows_by_orchestrator: dict[str, list[dict[str, Any]]] = {}

    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if not _is_workflow_orchestrator(infra, service):
                continue

            orchestrator = _orchestrator_row(bundle, service)
            orchestrator_id = orchestrator["id"]
            try:
                workflows = _workflow_rows(service)
            except Exception as exc:
                workflows = []
                orchestrator["message"] = f"Failed to load workflows: {exc}"
            orchestrator["workflow_count"] = len(workflows)
            orchestrator["active_workflow_count"] = sum(
                1 for workflow in workflows if workflow.get("is_active") is True
            )
            orchestrator["paused_workflow_count"] = sum(
                1 for workflow in workflows if workflow.get("is_paused") is True
            )
            orchestrators.append(orchestrator)
            workflows_by_orchestrator[orchestrator_id] = workflows

    return OperationResult(
        True,
        0,
        "Workflow orchestrators loaded."
        if orchestrators
        else "No workflow orchestrators found.",
        {
            "orchestrators": orchestrators,
            "workflows_by_orchestrator": workflows_by_orchestrator,
            "metrics": _metrics(orchestrators, workflows_by_orchestrator),
        },
    )


def add_workflow_repository(
    workspace,
    orchestrator_id: str,
    params: dict[str, str],
    *,
    config_loader=load_service_config_by_id,
) -> OperationResult:
    """Add a GitHub repository directly as a DAG source for one orchestrator."""

    resolved = _resolve_orchestrator(workspace, orchestrator_id)
    if not resolved.success:
        return resolved
    bundle = resolved.data["bundle"]
    orchestrator = resolved.data["service"]
    path_dags = str(getattr(orchestrator, "path_dags", "") or "")
    if not path_dags:
        return OperationResult(False, 84, "Selected orchestrator has no DAG path.")

    config = config_loader(GITHUB_REPOSITORY_TEMPLATE_ID)
    if not config:
        return OperationResult(False, 85, "GitHub repository template was not found.")

    add_service = getattr(workspace, "add_service_from_config", None)
    setup_service = getattr(workspace, "setup_service", None)
    if not callable(add_service) or not callable(setup_service):
        return OperationResult(False, 86, "Project workspace cannot add services.")

    result = add_service(config, server_ip=getattr(bundle.server, "ip", ""), params=params)
    if not result.success:
        return result
    service = result.data.get("service") if result.data else None
    if service is None:
        return OperationResult(False, 87, "Added repository service was not returned.")

    repo_name = str(getattr(service, "repo_name", "") or params.get("${GITHUB_NAME}") or "")
    service.target_path = path_dags
    service.orchestrator_uuid = str(orchestrator_id)
    if repo_name:
        service.name = _unique_service_name(
            workspace,
            f"{repo_name} [Airflow DAG]",
            service,
        )

    setup = setup_service(name=service.name)
    if not setup.success:
        return setup

    clone_error = _clone_workflow_repository(bundle, service)
    commit = getattr(workspace, "commit", None)
    if callable(commit):
        commit()
    row = _repository_row(bundle, service)
    if clone_error:
        return OperationResult(
            False,
            88,
            f"Workflow repository was added but clone failed: {clone_error}",
            {"repository": row},
        )

    return OperationResult(
        True,
        0,
        f"Added DAG repository {service.name}.",
        {"repository": row},
    )


def describe_workflow_secret_managers(workspace, orchestrator_id: str) -> OperationResult:
    """Return keyfile-exportable secret managers for workflow env exposure."""

    resolved = _resolve_orchestrator(workspace, orchestrator_id)
    if not resolved.success:
        return resolved
    orchestrator = resolved.data["service"]

    managers: list[dict[str, Any]] = []
    list_managers = getattr(workspace, "list_secret_managers", None)
    probe_manager = getattr(workspace, "probe_secret_manager", None)
    if not callable(list_managers) or not callable(probe_manager):
        return OperationResult(False, 89, "Project workspace cannot list secret managers.")

    for descriptor in list_managers():
        manager_id = str(getattr(descriptor, "id", "") or "")
        if not manager_id:
            continue
        try:
            probed = probe_manager(manager_id)
        except Exception as exc:
            managers.append(
                {
                    "id": manager_id,
                    "name": str(getattr(descriptor, "name", manager_id)),
                    "kind": str(getattr(descriptor, "kind", "-")),
                    "available": False,
                    "supports_keyfile_export": False,
                    "message": str(exc),
                }
            )
            continue
        available = bool(getattr(probed, "is_available", False))
        supports = bool(getattr(probed, "supports_keyfile_export", False))
        if not available or not supports:
            continue
        managers.append(
            {
                "id": manager_id,
                "name": str(getattr(probed, "name", manager_id)),
                "kind": str(getattr(probed, "kind", "-")),
                "available": available,
                "supports_keyfile_export": supports,
                "selected": manager_id
                == str(getattr(orchestrator, "workflow_secret_manager_uuid", "") or ""),
                "message": "",
            }
        )

    return OperationResult(
        True,
        0,
        "Workflow secret managers loaded."
        if managers
        else "No keyfile-exportable secret managers found.",
        {
            "managers": managers,
            "selected_manager_id": str(
                getattr(orchestrator, "workflow_secret_manager_uuid", "") or ""
            ),
        },
    )


def expose_secret_manager_to_workflow_orchestrator(
    workspace,
    orchestrator_id: str,
    manager_id: str,
) -> OperationResult:
    """Expose one selected secret manager to an orchestrator through env vars."""

    resolved = _resolve_orchestrator(workspace, orchestrator_id)
    if not resolved.success:
        return resolved
    bundle = resolved.data["bundle"]
    orchestrator = resolved.data["service"]

    probe_manager = getattr(workspace, "probe_secret_manager", None)
    if not callable(probe_manager):
        return OperationResult(False, 89, "Project workspace cannot list secret managers.")
    try:
        descriptor = probe_manager(manager_id)
    except Exception as exc:
        return OperationResult(False, 90, f"Secret manager is unavailable: {exc}")
    if not getattr(descriptor, "is_available", False):
        return OperationResult(False, 91, "Selected secret manager is unavailable.")
    if not getattr(descriptor, "supports_keyfile_export", False):
        return OperationResult(
            False,
            92,
            "Selected secret manager cannot export keyfile credentials.",
        )
    manager = getattr(descriptor, "manager", None)
    if manager is None:
        return OperationResult(False, 91, "Selected secret manager is unavailable.")

    password = generate_pw(16)
    application_name = f"airflow-{orchestrator_id}"
    service = getattr(descriptor, "service", None)
    create_keyfile_manager = getattr(service, "create_keyfile_secret_manager", None)
    if callable(create_keyfile_manager):
        try:
            manager = create_keyfile_manager(
                getattr(workspace, "infrastructure", None),
                application_name=application_name,
                period="24h",
            )
            credentials = getattr(service, "application_credentials", {}) or {}
            if application_name in credentials:
                credentials[application_name]["keyfile_password"] = password
        except Exception as exc:
            return OperationResult(
                False,
                93,
                f"Could not create application credential: {exc}",
            )

    try:
        keyfile = get_encrypted_access_keyfile(manager, password)
    except Exception as exc:
        return OperationResult(False, 94, f"Could not export secret-manager keyfile: {exc}")

    setter = getattr(orchestrator, "set_workflow_secret_manager_env", None)
    if not callable(setter):
        return OperationResult(
            False,
            95,
            "Selected orchestrator cannot expose secret-manager credentials.",
        )

    with bundle.server.get_server_connection() as conn:
        setter(
            conn,
            manager_uuid=manager_id,
            encrypted_keyfile=keyfile,
            keyfile_password=password,
        )
    commit = getattr(workspace, "commit", None)
    if callable(commit):
        commit()

    return OperationResult(
        True,
        0,
        f"Exposed {getattr(descriptor, 'name', manager_id)} to {orchestrator.name}.",
        {
            "manager_id": manager_id,
            "orchestrator_id": orchestrator_id,
            "env": {
                SECRET_MANAGER_KEYFILE_ENV: "hidden",
                SECRET_MANAGER_KEYFILE_PW_ENV: "hidden",
            },
        },
    )


def _resolve_orchestrator(workspace, orchestrator_id: str) -> OperationResult:
    selected_id = str(orchestrator_id).strip()
    if not selected_id:
        return OperationResult(False, 81, "No workflow orchestrator selected.")
    if not workspace:
        return OperationResult(False, 82, "Project workspace is unavailable.")
    infra = getattr(workspace, "infrastructure", None)
    if infra is None:
        return OperationResult(False, 80, "Infrastructure is unavailable.")

    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            service_id = str(getattr(service, "uuid", "") or "")
            if service_id == selected_id and _is_workflow_orchestrator(infra, service):
                return OperationResult(
                    True,
                    0,
                    "Workflow orchestrator resolved.",
                    {"bundle": bundle, "service": service},
                )
    return OperationResult(False, 83, "Workflow orchestrator not found.")


def _clone_workflow_repository(bundle, service) -> str:
    if bool(getattr(service, "cloned", False)):
        return ""
    git_clone = getattr(service, "git_clone", None)
    if not callable(git_clone):
        return "Repository service cannot clone."
    try:
        with bundle.server.get_server_connection() as conn:
            git_clone(conn)
    except Exception as exc:
        return str(exc)
    return ""


def _repository_row(bundle, service) -> dict[str, Any]:
    summary = _repository_summary(service)
    return {
        "id": str(getattr(service, "uuid", "") or ""),
        "name": str(summary.get("name") or getattr(service, "name", "-")),
        "bundle": str(getattr(bundle, "name", "-")),
        "server": str(getattr(getattr(bundle, "server", None), "ip", "-")),
        "root": str(summary.get("root") or ""),
        "url": str(summary.get("url") or ""),
        "private": bool(summary.get("private", False)),
        "cloned": bool(summary.get("cloned", False)),
        "orchestrator_uuid": getattr(service, "orchestrator_uuid", None),
    }


def _repository_summary(service) -> dict[str, Any]:
    summary = getattr(service, "repository_summary", None)
    if callable(summary):
        return summary() or {}
    return {
        "name": str(getattr(service, "repo_name", "") or getattr(service, "name", "-")),
        "root": str(getattr(service, "target_path", "") or ""),
        "url": str(getattr(service, "link", "") or ""),
        "private": bool(getattr(service, "is_private", False)),
        "cloned": bool(getattr(service, "cloned", False)),
    }


def _unique_service_name(workspace, desired_name: str, service) -> str:
    infra = getattr(workspace, "infrastructure", None)
    if infra is None:
        return desired_name

    names: set[str] = set()
    for bundle in getattr(infra, "bundles", []) or []:
        for existing in getattr(bundle, "services", []) or []:
            if existing is service:
                continue
            name = str(getattr(existing, "name", "") or "")
            if name:
                names.add(name)

    if desired_name not in names:
        return desired_name

    counter = 0
    while True:
        candidate = f"{desired_name}_{counter}"
        if candidate not in names:
            return candidate
        counter += 1


def _orchestrator_row(bundle, service) -> dict[str, Any]:
    service_id = str(getattr(service, "uuid", getattr(service, "name", "")))
    urls = getattr(service, "service_urls", {}) or {}
    workflow_repositories = [
        repo
        for repo in getattr(bundle, "services", []) or []
        if getattr(repo, "orchestrator_uuid", None) == service_id
    ]
    return {
        "id": service_id,
        "name": str(getattr(service, "name", "-")),
        "bundle": str(getattr(bundle, "name", "-")),
        "server": str(getattr(getattr(bundle, "server", None), "ip", "-")),
        "state": str(getattr(service, "state", "unknown")),
        "type": str(getattr(service, "service_config_id", "workflow-orchestrator")),
        "url": str(
            next(iter(urls.values()), getattr(service, "service_url", "") or "")
        ),
        "workflow_count": 0,
        "active_workflow_count": 0,
        "paused_workflow_count": 0,
        "repository_count": len(workflow_repositories),
        "workflow_secret_manager_uuid": str(
            getattr(service, "workflow_secret_manager_uuid", "") or ""
        ),
        "secret_manager_status": "Exposed"
        if getattr(service, "workflow_secret_manager_uuid", None)
        else "Not exposed",
        "message": "",
        "service_ref": service,
        "bundle_ref": bundle,
    }


def _workflow_rows(service) -> list[dict[str, Any]]:
    list_workflows = getattr(service, "list_workflows", None)
    if not callable(list_workflows):
        return [
            {
                "id": "-",
                "name": "-",
                "schedule": "-",
                "is_paused": None,
                "is_active": None,
                "last_run_state": "",
                "last_run_start": "",
                "last_run_end": "",
                "message": "Workflow listing is not supported by this service.",
            }
        ]

    rows: list[dict[str, Any]] = []
    for workflow in list(list_workflows() or []):
        if not isinstance(workflow, dict):
            continue
        rows.append(
            {
                "id": str(workflow.get("id") or workflow.get("name") or "-"),
                "name": str(workflow.get("name") or workflow.get("id") or "-"),
                "schedule": str(workflow.get("schedule") or "-"),
                "is_paused": workflow.get("is_paused"),
                "is_active": workflow.get("is_active"),
                "owners": str(workflow.get("owners") or ""),
                "tags": str(workflow.get("tags") or ""),
                "fileloc": str(workflow.get("fileloc") or ""),
                "last_run_id": str(workflow.get("last_run_id") or ""),
                "last_run_state": str(workflow.get("last_run_state") or ""),
                "last_run_start": str(workflow.get("last_run_start") or ""),
                "last_run_end": str(workflow.get("last_run_end") or ""),
                "message": str(workflow.get("message") or ""),
            }
        )
    return rows


def _metrics(
    orchestrators: list[dict[str, Any]],
    workflows_by_orchestrator: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    workflows = [
        workflow
        for rows in workflows_by_orchestrator.values()
        for workflow in rows
    ]
    return {
        "orchestrators": len(orchestrators),
        "running_orchestrators": sum(
            1 for row in orchestrators if row.get("state") == "running"
        ),
        "workflows": len(workflows),
        "active_workflows": sum(
            1 for workflow in workflows if workflow.get("is_active") is True
        ),
        "paused_workflows": sum(
            1 for workflow in workflows if workflow.get("is_paused") is True
        ),
    }


def _is_workflow_orchestrator(infra, service) -> bool:
    capabilities = {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in (getattr(service, "capabilities", set()) or set())
    }
    if ServiceCapability.WORKFLOW_ORCHESTRATOR.value in capabilities:
        return True

    get_config = getattr(infra, "get_service_config", None)
    config = get_config(service) if callable(get_config) else None
    service_capabilities = (
        config.service_capabilities()
        if config and hasattr(config, "service_capabilities")
        else set()
    )
    return ServiceCapability.WORKFLOW_ORCHESTRATOR.value in service_capabilities
