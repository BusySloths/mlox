from __future__ import annotations

from typing import Any

from mlox.application.result import OperationResult
from mlox.service import ServiceCapability


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


def _orchestrator_row(bundle, service) -> dict[str, Any]:
    service_id = str(getattr(service, "uuid", getattr(service, "name", "")))
    urls = getattr(service, "service_urls", {}) or {}
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
