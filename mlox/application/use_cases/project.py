from __future__ import annotations

from copy import deepcopy
from typing import Any

from mlox.application.result import OperationResult


def create_project(project) -> OperationResult:
    return OperationResult(
        True,
        0,
        f"Created project '{project.name}'.",
        {"project": project},
    )


def open_project_workspace(
    project_path: str,
    password: str,
    *,
    create: bool = False,
    workspace_cls=None,
) -> OperationResult:
    """Open or create a project workspace for UI adapters."""

    from mlox.project import (
        InvalidProjectPasswordError,
        ProjectAlreadyExistsError,
        ProjectNotFoundError,
        ProjectStorageError,
        ProjectWorkspace,
    )

    workspace_cls = workspace_cls or ProjectWorkspace
    try:
        workspace = (
            workspace_cls.create(project_path, password)
            if create
            else workspace_cls.open(project_path, password)
        )
    except ProjectNotFoundError:
        return OperationResult(False, 1, "Project not found")
    except ProjectAlreadyExistsError:
        return OperationResult(False, 2, "Project already exists; use Open")
    except InvalidProjectPasswordError:
        return OperationResult(False, 3, "Invalid project password")
    except (ProjectStorageError, ValueError) as exc:
        return OperationResult(False, 4, str(exc))

    return OperationResult(
        True,
        0,
        f"Opened project '{workspace.name}'.",
        {"workspace": workspace},
    )


def reload_project_workspace(workspace) -> OperationResult:
    """Reload an already-open project workspace."""

    try:
        workspace.reload()
    except Exception as exc:
        return OperationResult(
            False,
            5,
            f"Failed to reload infrastructure: {exc}",
        )

    return OperationResult(
        True,
        0,
        f"Reloaded project infrastructure for {workspace.path}.",
        {"workspace": workspace},
    )


def rename_project_workspace(workspace, name: str) -> OperationResult:
    """Rename an already-open project workspace and persist the metadata."""

    new_name = name.strip()
    if not new_name:
        return OperationResult(False, 6, "Project name must not be empty.")

    old_name = getattr(workspace, "name", "")
    try:
        workspace.name = new_name
        commit = getattr(workspace, "commit", None)
        if callable(commit):
            commit()
    except Exception as exc:
        try:
            workspace.name = old_name
        except Exception:
            pass
        return OperationResult(False, 7, f"Failed to rename project: {exc}")

    return OperationResult(
        True,
        0,
        f"Renamed project '{old_name}' to '{new_name}'.",
        {"workspace": workspace},
    )


def update_bundle_tags(workspace, bundle, tags: list[str]) -> OperationResult:
    """Update tags for a bundle in an open project workspace."""

    normalized_tags = _normalize_tags(tags)
    old_tags = list(getattr(bundle, "tags", []) or [])
    try:
        bundle.tags = normalized_tags
        commit = getattr(workspace, "commit", None)
        if callable(commit):
            commit()
    except Exception as exc:
        try:
            bundle.tags = old_tags
        except Exception:
            pass
        return OperationResult(False, 8, f"Failed to update bundle tags: {exc}")

    return OperationResult(
        True,
        0,
        f"Updated tags for bundle '{getattr(bundle, 'name', '-')}'.",
        {"workspace": workspace, "bundle": bundle, "tags": normalized_tags},
    )


def summarize_infrastructure(workspace) -> OperationResult:
    """Return aggregate statistics and listings for the active workspace."""

    summary: dict[str, Any] = {
        "has_data": False,
        "totals": {"bundles": 0, "servers": 0, "services": 0, "cpu": 0.0, "ram": 0.0},
        "cpu_available": False,
        "ram_available": False,
        "server_rows": [],
        "service_rows": [],
    }
    if not workspace:
        return OperationResult(True, 0, "No workspace loaded.", {"summary": summary})

    infra = getattr(workspace, "infrastructure", None)
    bundles = getattr(infra, "bundles", None)
    if not infra or not bundles:
        return OperationResult(
            True,
            0,
            "No infrastructure available.",
            {"summary": summary},
        )

    summary["has_data"] = True
    summary["totals"]["bundles"] = len(bundles)
    for bundle in bundles:
        services = getattr(bundle, "services", []) or []
        server = getattr(bundle, "server", None)
        if server:
            summary["totals"]["servers"] += 1
            summary["server_rows"].append(
                (
                    getattr(server, "ip", "unknown"),
                    ", ".join(_server_backends(server)) or "unknown",
                    ", ".join(_server_capabilities(server)) or "-",
                    getattr(server, "state", "unknown"),
                    len(services),
                )
            )
            _add_server_resource_totals(summary, server)
        for svc in services:
            summary["totals"]["services"] += 1
            summary["service_rows"].append(
                (
                    getattr(svc, "name", "-"),
                    getattr(svc, "service_config_id", "-"),
                    getattr(server, "ip", "unknown") if server else "-",
                    getattr(svc, "state", "unknown"),
                )
            )
    return OperationResult(
        True,
        0,
        "Infrastructure summary loaded.",
        {"summary": summary},
    )


def describe_secret_manager(workspace) -> OperationResult:
    """Return redacted metadata for the active project secret manager."""

    if not workspace:
        return OperationResult(False, 9, "Project workspace is unavailable.")

    manager = getattr(workspace, "secrets", None)
    if manager is None:
        return OperationResult(False, 10, "No active secret manager is configured.")

    status = "unknown"
    try:
        status = "available" if manager.is_working() else "unavailable"
    except Exception as exc:
        return OperationResult(
            True,
            0,
            "Secret manager is unavailable.",
            {
                "manager": _secret_manager_metadata(workspace, manager, "unavailable"),
                "secrets": [],
                "error": str(exc),
            },
        )

    try:
        listed = manager.list_secrets(keys_only=True)
    except Exception as exc:
        return OperationResult(
            True,
            0,
            "Could not list secret keys.",
            {
                "manager": _secret_manager_metadata(workspace, manager, status),
                "secrets": [],
                "error": str(exc),
            },
        )

    secret_names = sorted(str(name) for name in (listed or {}).keys())
    secrets = [
        {
            "name": name,
            "value": "hidden",
        }
        for name in secret_names
    ]
    return OperationResult(
        True,
        0,
        "Secret manager metadata loaded.",
        {
            "manager": _secret_manager_metadata(workspace, manager, status),
            "secrets": secrets,
            "error": "",
        },
    )


def reveal_secret(workspace, name: str) -> OperationResult:
    """Load one secret value from the active project secret manager."""

    secret_name = str(name).strip()
    if not secret_name:
        return OperationResult(False, 11, "No secret selected.")
    if not workspace:
        return OperationResult(False, 12, "Project workspace is unavailable.")

    manager = getattr(workspace, "secrets", None)
    if manager is None:
        return OperationResult(False, 13, "No active secret manager is configured.")

    try:
        value = manager.load_secret(secret_name)
    except Exception as exc:
        return OperationResult(
            False,
            14,
            f"Could not load secret '{secret_name}': {exc}",
        )

    if value is None:
        return OperationResult(False, 15, f"Secret '{secret_name}' was not found.")

    return OperationResult(
        True,
        0,
        f"Loaded secret '{secret_name}'.",
        {"name": secret_name, "value": deepcopy(value)},
    )


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        value = str(tag).strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _secret_manager_metadata(workspace, manager, status: str) -> dict[str, Any]:
    return {
        "name": str(getattr(workspace, "active_secret_manager_name", "Unknown")),
        "kind": str(getattr(workspace, "secret_manager_kind", "unknown")),
        "status": status,
        "class": manager.__class__.__name__,
        "supports_keyfile_export": bool(
            getattr(manager, "supports_keyfile_export", False)
        ),
    }


def _server_backends(server) -> list[str]:
    raw_backends = getattr(server, "backend", []) if server else []
    if isinstance(raw_backends, str):
        raw_backends = [raw_backends]
    return [
        str(backend).strip().lower().replace("-", "_")
        for backend in raw_backends or []
        if str(backend).strip()
    ]


def _server_capabilities(server) -> list[str]:
    raw_capabilities = getattr(server, "capabilities", set()) if server else set()
    capabilities = set()
    for capability in raw_capabilities or []:
        value = capability.value if hasattr(capability, "value") else capability
        name = str(value).strip().replace("-", "_")
        if name:
            capabilities.add(name)
    return sorted(capabilities)


def _add_server_resource_totals(summary: dict[str, Any], server) -> None:
    try:
        info = server.get_server_info()
    except Exception:
        info = {}
    cpu_count = info.get("cpu_count") if isinstance(info, dict) else None
    ram_gb = info.get("ram_gb") if isinstance(info, dict) else None
    if isinstance(cpu_count, (int, float)):
        summary["cpu_available"] = True
        summary["totals"]["cpu"] += float(cpu_count)
    if isinstance(ram_gb, (int, float)):
        summary["ram_available"] = True
        summary["totals"]["ram"] += float(ram_gb)
