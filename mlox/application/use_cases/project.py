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
