from __future__ import annotations

import posixpath
from typing import Any

from mlox.application.result import OperationResult
from mlox.service import AbstractRepositoryService, ServiceCapability

MAX_REPOSITORY_FILE_BYTES = 512 * 1024


def describe_repositories(infra) -> OperationResult:
    """Return project repository services without remote IO."""

    if infra is None:
        return OperationResult(False, 60, "Infrastructure is unavailable.")

    rows = []
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if _is_repository_service(infra, service):
                rows.append(_repository_row(bundle, service))

    return OperationResult(
        True,
        0,
        "Repository services loaded." if rows else "No repository services found.",
        {"repositories": rows, "metrics": _metrics(rows)},
    )


def refresh_repository(workspace, repository_id: str) -> OperationResult:
    """Load status and file tree for one repository service."""

    resolved = _resolve_repository(workspace, repository_id)
    if not resolved.success:
        return resolved

    bundle = resolved.data["bundle"]
    service = resolved.data["service"]
    return _with_repository_connection(
        bundle,
        lambda conn: _refresh_with_connection(bundle, service, conn),
    )


def clone_repository(workspace, repository_id: str) -> OperationResult:
    """Clone the selected repository and persist service state."""

    return _run_repository_action(
        workspace,
        repository_id,
        action="clone",
        message="Repository cloned.",
    )


def pull_repository(workspace, repository_id: str) -> OperationResult:
    """Pull the selected repository and persist service state."""

    return _run_repository_action(
        workspace,
        repository_id,
        action="pull",
        message="Repository pulled.",
    )


def get_repository_deploy_keys(workspace, repository_id: str) -> OperationResult:
    """Return deploy keys for the selected repository."""

    resolved = _resolve_repository(workspace, repository_id)
    if not resolved.success:
        return resolved

    service = resolved.data["service"]
    get_keys = getattr(service, "get_deploy_keys", None)
    keys = get_keys() if callable(get_keys) else {}
    return OperationResult(
        True,
        0,
        "Repository deploy keys loaded." if keys else "No deploy keys available.",
        {"keys": {str(key): str(value) for key, value in (keys or {}).items()}},
    )


def read_repository_file(
    workspace,
    repository_id: str,
    path: str,
    *,
    max_bytes: int = MAX_REPOSITORY_FILE_BYTES,
) -> OperationResult:
    """Read one text file from a repository after validating it is safe to view."""

    resolved = _resolve_repository(workspace, repository_id)
    if not resolved.success:
        return resolved

    bundle = resolved.data["bundle"]
    service = resolved.data["service"]
    root = _repository_root(service)
    requested_path = _normalize_requested_path(root, path)
    if not _path_is_inside(root, requested_path):
        return OperationResult(False, 72, "Selected file is outside the repository.")

    def read_with_connection(conn):
        status = _repository_status(service, conn)
        summary = _repository_summary(service)
        cloned = bool(status.get("cloned", summary.get("cloned", False)))
        if not cloned:
            return OperationResult(False, 77, "Repository is not cloned yet.")
        tree = _repository_tree(service, conn)
        entry = _tree_entry_by_path(tree, requested_path)
        if not entry:
            return OperationResult(False, 73, "Selected file was not found.")
        if entry.get("is_dir"):
            return OperationResult(False, 74, "Selected path is a directory.")
        size = int(entry.get("size") or 0)
        if size > max_bytes:
            return OperationResult(
                False,
                75,
                f"Selected file is too large to view ({size} bytes).",
                {"path": requested_path, "size": size},
            )
        content = service.read_repository_file(conn, requested_path)
        return OperationResult(
            True,
            0,
            "Repository file loaded.",
            {
                "path": requested_path,
                "name": str(entry.get("name") or posixpath.basename(requested_path)),
                "size": size,
                "content": str(content),
            },
        )

    return _with_repository_connection(bundle, read_with_connection)


def _run_repository_action(
    workspace,
    repository_id: str,
    *,
    action: str,
    message: str,
) -> OperationResult:
    resolved = _resolve_repository(workspace, repository_id)
    if not resolved.success:
        return resolved

    bundle = resolved.data["bundle"]
    service = resolved.data["service"]

    def run_with_connection(conn):
        try:
            if action == "clone":
                service.git_clone(conn)
            else:
                service.git_pull(conn)
            commit = getattr(workspace, "commit", None)
            if callable(commit):
                commit()
        except Exception as exc:
            return OperationResult(False, 76, f"Failed to {action} repository: {exc}")

        refreshed = _refresh_with_connection(bundle, service, conn)
        if not refreshed.success:
            return refreshed
        refreshed.message = message
        return refreshed

    return _with_repository_connection(bundle, run_with_connection)


def _resolve_repository(workspace, repository_id: str) -> OperationResult:
    selected_id = str(repository_id).strip()
    if not selected_id:
        return OperationResult(False, 61, "No repository selected.")
    if not workspace:
        return OperationResult(False, 62, "Project workspace is unavailable.")

    infra = getattr(workspace, "infrastructure", None)
    if infra is None:
        return OperationResult(False, 60, "Infrastructure is unavailable.")

    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if _repository_id(service) == selected_id and _is_repository_service(
                infra, service
            ):
                return OperationResult(
                    True,
                    0,
                    "Repository resolved.",
                    {"bundle": bundle, "service": service},
                )
    return OperationResult(False, 63, "Repository service not found.")


def _with_repository_connection(bundle, operation) -> OperationResult:
    server = getattr(bundle, "server", None)
    connection_factory = getattr(server, "get_server_connection", None)
    if not callable(connection_factory):
        return OperationResult(False, 64, "Repository server cannot open a connection.")
    try:
        with connection_factory() as conn:
            return operation(conn)
    except Exception as exc:
        return OperationResult(False, 65, f"Repository operation failed: {exc}")


def _refresh_with_connection(bundle, service, conn) -> OperationResult:
    status = _repository_status(service, conn)
    try:
        summary = _repository_summary(service)
        cloned = bool(status.get("cloned", summary.get("cloned", False)))
        if cloned:
            raw_tree = status.get("tree") or _repository_tree(service, conn)
            tree = _normalize_tree(raw_tree, _repository_root(service))
        else:
            status.setdefault("message", "Repository is not cloned yet.")
            tree = []
    except Exception as exc:
        status["message"] = f"Failed to load repository tree: {exc}"
        tree = []

    row = _repository_row(bundle, service, status=status, tree=tree)
    return OperationResult(
        True,
        0,
        "Repository refreshed.",
        {"repository": row, "tree": tree},
    )


def _repository_status(service, conn) -> dict[str, Any]:
    check = getattr(service, "check", None)
    if not callable(check):
        return {"message": "Repository status is not supported."}
    try:
        status = check(conn) or {}
        return status if isinstance(status, dict) else {"message": str(status)}
    except Exception as exc:
        return {"message": f"Failed to load repository status: {exc}"}


def _repository_tree(service, conn) -> list[dict[str, Any]]:
    list_tree = getattr(service, "list_repository_tree", None)
    if callable(list_tree):
        return list(list_tree(conn) or [])
    return []


def _repository_row(
    bundle,
    service,
    *,
    status: dict[str, Any] | None = None,
    tree: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = status or {}
    summary = _repository_summary(service)
    cloned = bool(status.get("cloned", summary.get("cloned", False)))
    private = bool(status.get("private", summary.get("private", False)))
    exists = status.get("exists")
    get_keys = getattr(service, "get_deploy_keys", None)
    deploy_keys = get_keys() if callable(get_keys) else {}
    return {
        "id": _repository_id(service),
        "name": str(summary.get("name") or getattr(service, "name", "-")),
        "service": str(getattr(service, "name", "-")),
        "bundle": str(getattr(bundle, "name", "-")),
        "server": str(getattr(getattr(bundle, "server", None), "ip", "-")),
        "state": str(summary.get("state") or getattr(service, "state", "unknown")),
        "visibility": "private" if private else "public",
        "private": private,
        "cloned": cloned,
        "exists": exists if isinstance(exists, bool) else None,
        "url": str(summary.get("url") or ""),
        "root": str(summary.get("root") or _repository_root(service)),
        "orchestrator_uuid": summary.get(
            "orchestrator_uuid",
            getattr(service, "orchestrator_uuid", None),
        ),
        "created": str(summary.get("created") or ""),
        "modified": str(summary.get("modified") or ""),
        "deploy_keys_available": bool(deploy_keys),
        "file_count": sum(1 for entry in tree or [] if entry.get("is_file")),
        "directory_count": sum(1 for entry in tree or [] if entry.get("is_dir")),
        "message": str(status.get("message") or ""),
    }


def _repository_summary(service) -> dict[str, Any]:
    summary = getattr(service, "repository_summary", None)
    if callable(summary):
        return summary() or {}
    get_url = getattr(service, "get_url", None)
    url = get_url() if callable(get_url) else ""
    return {
        "name": str(getattr(service, "repo_name", "") or getattr(service, "name", "-")),
        "url": str(url or ""),
        "root": _repository_root(service),
        "orchestrator_uuid": getattr(service, "orchestrator_uuid", None),
        "private": bool(getattr(service, "is_private", False)),
        "cloned": bool(getattr(service, "cloned", False)),
        "state": str(getattr(service, "state", "unknown")),
        "created": str(getattr(service, "created_timestamp", "") or ""),
        "modified": str(getattr(service, "modified_timestamp", "") or ""),
    }


def _repository_root(service) -> str:
    root = getattr(service, "get_repository_root", None)
    if callable(root):
        return str(root() or "")
    target_path = str(getattr(service, "target_path", "") or "").rstrip("/")
    repo_name = str(getattr(service, "repo_name", "") or "").strip("/")
    return f"{target_path}/{repo_name}" if target_path and repo_name else target_path


def _normalize_tree(entries: list[dict[str, Any]], root: str) -> list[dict[str, Any]]:
    root_path = _normalize_absolute_path(root)
    normalized = []
    for entry in entries or []:
        path = _normalize_absolute_path(str(entry.get("path") or ""))
        if not path or path == root_path:
            continue
        if root_path and not _path_is_inside(root_path, path):
            continue
        display_path = path[len(root_path) :].lstrip("/") if root_path else path
        if not display_path or _is_hidden_git_path(display_path):
            continue
        normalized.append(
            {
                "name": str(entry.get("name") or posixpath.basename(path)),
                "path": path,
                "display_path": display_path,
                "is_file": bool(entry.get("is_file")),
                "is_dir": bool(entry.get("is_dir")),
                "size": int(entry.get("size") or 0),
                "modification_datetime": str(
                    entry.get("modification_datetime") or ""
                ),
            }
        )
    return sorted(
        normalized,
        key=lambda item: (
            str(item.get("display_path", "")).count("/"),
            not item.get("is_dir", False),
            str(item.get("display_path", "")).lower(),
        ),
    )


def _tree_entry_by_path(entries: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    normalized_path = _normalize_absolute_path(path)
    for entry in entries or []:
        if _normalize_absolute_path(str(entry.get("path") or "")) == normalized_path:
            return entry
    return None


def _normalize_requested_path(root: str, path: str) -> str:
    value = str(path or "").strip()
    if not value:
        return _normalize_absolute_path(root)
    if value.startswith("/"):
        return _normalize_absolute_path(value)
    return _normalize_absolute_path(f"{root.rstrip('/')}/{value}")


def _normalize_absolute_path(path: str) -> str:
    value = posixpath.normpath(str(path or ""))
    return "" if value == "." else value


def _path_is_inside(root: str, path: str) -> bool:
    root_path = _normalize_absolute_path(root)
    child_path = _normalize_absolute_path(path)
    return bool(
        root_path
        and child_path
        and (child_path == root_path or child_path.startswith(f"{root_path}/"))
    )


def _is_hidden_git_path(display_path: str) -> bool:
    return any(part == ".git" for part in str(display_path).split("/"))


def _is_repository_service(infra, service) -> bool:
    if isinstance(service, AbstractRepositoryService):
        return True
    capabilities = {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in (getattr(service, "capabilities", set()) or set())
    }
    if ServiceCapability.REPOSITORY.value in capabilities or "repository" in capabilities:
        return True

    get_config = getattr(infra, "get_service_config", None)
    config = get_config(service) if callable(get_config) else None
    service_capabilities = (
        config.service_capabilities()
        if config and hasattr(config, "service_capabilities")
        else set()
    )
    service_capability_values = {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in service_capabilities
    }
    return ServiceCapability.REPOSITORY.value in service_capability_values


def _repository_id(service) -> str:
    return str(getattr(service, "uuid", "") or getattr(service, "name", ""))


def _metrics(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "cloned": sum(1 for row in rows if row.get("cloned")),
        "private": sum(1 for row in rows if row.get("private")),
        "available": sum(
            1
            for row in rows
            if row.get("state") in {"running", "ready"} or row.get("cloned")
        ),
    }
