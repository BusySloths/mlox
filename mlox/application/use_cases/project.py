from __future__ import annotations

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


def rename_bundle(workspace, bundle, name: str) -> OperationResult:
    """Rename one bundle in an open project workspace."""

    new_name = name.strip()
    if not new_name:
        return OperationResult(False, 11, "Bundle name must not be empty.")

    infra = getattr(workspace, "infrastructure", None)
    bundles = getattr(infra, "bundles", []) or []
    for candidate in bundles:
        if candidate is bundle:
            continue
        if str(getattr(candidate, "name", "")).casefold() == new_name.casefold():
            return OperationResult(
                False,
                12,
                f"Bundle name '{new_name}' is already in use.",
            )

    old_name = getattr(bundle, "name", "")
    try:
        bundle.name = new_name
        commit = getattr(workspace, "commit", None)
        if callable(commit):
            commit()
    except Exception as exc:
        try:
            bundle.name = old_name
        except Exception:
            pass
        return OperationResult(False, 13, f"Failed to rename bundle: {exc}")

    return OperationResult(
        True,
        0,
        f"Renamed bundle '{old_name}' to '{new_name}'.",
        {"workspace": workspace, "bundle": bundle},
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
        "totals": {
            "bundles": 0,
            "servers": 0,
            "services": 0,
            "cpu": 0.0,
            "ram": 0.0,
        },
        "cpu_available": False,
        "ram_available": False,
        "server_rows": [],
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
        service_states = _count_service_states(services)
        if server:
            summary["totals"]["servers"] += 1
            summary["server_rows"].append(
                {
                    "bundle": getattr(bundle, "name", "-"),
                    "server": getattr(server, "ip", "unknown"),
                    "backend": ", ".join(_server_backends(server)) or "unknown",
                    "state": getattr(server, "state", "unknown"),
                    "services": len(services),
                    "service_states": service_states,
                }
            )
            _add_server_resource_totals(summary, server)
        summary["totals"]["services"] += len(services)
    return OperationResult(
        True,
        0,
        "Infrastructure summary loaded.",
        {"summary": summary},
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


def _normalize_service_state(state: object) -> str:
    value = str(state or "unknown").strip().lower().replace("-", "_")
    return value or "unknown"


def _count_service_states(services: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for service in services:
        state = _service_state_bucket(getattr(service, "state", "unknown"))
        counts[state] = counts.get(state, 0) + 1
    return counts


def _service_state_bucket(state: object) -> str:
    value = _normalize_service_state(state)
    if value in {"un_initialized", "uninitialized", "not_initialized"}:
        return "un-initialized"
    if value in {"running", "healthy"}:
        return "running"
    if value in {"failed", "error", "unhealthy", "degraded", "unknown", "exited"}:
        return "error"
    return "other"


def _server_backends(server) -> list[str]:
    raw_backends = getattr(server, "backend", []) if server else []
    if isinstance(raw_backends, str):
        raw_backends = [raw_backends]
    return [
        str(backend).strip().lower().replace("-", "_")
        for backend in raw_backends or []
        if str(backend).strip()
    ]


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
