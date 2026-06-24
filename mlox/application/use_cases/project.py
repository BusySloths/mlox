from __future__ import annotations

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
