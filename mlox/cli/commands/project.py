from __future__ import annotations

from typing import Optional

import typer

from mlox.application import ProjectApplication
from mlox.cli.common import handle_result
from mlox.cli.context import PASSWORD_ENVVAR, PROJECT_ENVVAR, resolve_password
from mlox.project.store import resolve_project_path

project_app = typer.Typer(help="Manage MLOX projects")


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Project file (the .mlox suffix is optional)"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
) -> None:
    resolved_password = resolve_password(password)
    try:
        application = ProjectApplication.create(name, resolved_password)
    except Exception as exc:
        typer.echo(f"[ERROR] Failed to create project: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    result = handle_result(application.project_created())
    typer.echo(result.message)
    typer.echo("")
    typer.echo("Run the following to export the project credentials:")
    typer.echo(f"  export {PROJECT_ENVVAR}='{resolve_project_path(name)}'")
    typer.echo(f"  export {PASSWORD_ENVVAR}='<your-project-password>'")
