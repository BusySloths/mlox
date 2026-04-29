from __future__ import annotations

from typing import Optional

import typer

from mlox import operations as ops
from mlox.cli.common import handle_result
from mlox.cli.context import PASSWORD_ENVVAR, PROJECT_ENVVAR, resolve_password

project_app = typer.Typer(help="Manage MLOX projects")


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
) -> None:
    resolved_password = resolve_password(password)
    result = handle_result(ops.create_project(name=name, password=resolved_password))
    typer.echo(result.message)
    typer.echo("")
    typer.echo("Run the following to export the project credentials:")
    typer.echo(f"  export {PROJECT_ENVVAR}='{name}'")
    typer.echo(f"  export {PASSWORD_ENVVAR}='{resolved_password}'")
