from __future__ import annotations

from typing import Optional

import typer

from mlox.project import ProjectWorkspace, resolve_project_path
from mlox.cli.common import handle_result
from mlox.cli.context import PASSWORD_ENVVAR, PROJECT_ENVVAR, resolve_password
from mlox.application.result import OperationResult
from mlox.cli.generation import WorkspaceCommand, register_workspace_commands
from mlox.cli.rendering.results import render_inspection

project_app = typer.Typer(help="Manage MLOX projects")
register_workspace_commands(project_app, (
    WorkspaceCommand(name="inspect", method="inspect_project", help="Inspect the active project.", renderer=render_inspection),
))


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Project file (the .mlox suffix is optional)"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the project",
        show_default=False,
    ),
) -> None:
    resolved_password = resolve_password(password)
    try:
        workspace = ProjectWorkspace.create(name, resolved_password)
    except Exception as exc:
        handle_result(OperationResult(False, 1, f"Failed to create project: {exc}"))
        return
    result = handle_result(workspace.project_created())
    typer.echo(result.message)
    typer.echo("")
    typer.echo("Run the following to export the project credentials:")
    typer.echo(f"  export {PROJECT_ENVVAR}='{resolve_project_path(name)}'")
    typer.echo(f"  export {PASSWORD_ENVVAR}='<your-project-password>'")
