"""Generated server command group wiring."""

from __future__ import annotations

import typer
import time

from mlox.cli.generation import register_workspace_commands
from mlox.cli.specifications.server import SERVER_COMMANDS, SERVER_CONFIG_COMMANDS


server_app = typer.Typer(help="Manage servers in the project infrastructure")
server_configs_app = typer.Typer(help="Server configuration templates")
server_app.add_typer(server_configs_app, name="configs")

GENERATED_SERVER_COMMANDS = register_workspace_commands(server_app, SERVER_COMMANDS)
GENERATED_SERVER_CONFIG_COMMANDS = register_workspace_commands(
    server_configs_app,
    SERVER_CONFIG_COMMANDS,
)


@server_app.command("firewall-access-hold")
def firewall_access_hold(
    project: str | None = typer.Option(None, "--project", help="Project path"),
    password: str | None = typer.Option(None, "--password", help="Project password", show_default=False),
) -> None:
    """Renew this computer's access until Ctrl-C or process termination."""
    from mlox.application.firewall_client import firewall_client_id
    from mlox.application.use_cases.firewall_grants import grant_current_computer, remove_computer_grant
    from mlox.cli.common import json_output
    from mlox.cli.context import resolve_credentials
    from mlox.project import ProjectWorkspace

    if json_output():
        raise typer.BadParameter("The hold command is interactive; use firewall-access-add for JSON output.")
    project_path, project_password = resolve_credentials(project, password)
    workspace = ProjectWorkspace.open(project_path, project_password)
    ident = firewall_client_id()
    result = grant_current_computer(workspace.infrastructure, grant_id=ident, duration_seconds=300)
    typer.echo(result.message)
    if not any(row.get("status") == "added" for row in (result.data or {}).get("servers", [])):
        raise typer.Exit(result.code or 1)
    typer.echo("Renewing every two minutes. Press Ctrl-C to remove access.")
    try:
        while True:
            time.sleep(120)
            result = grant_current_computer(workspace.infrastructure, grant_id=ident, duration_seconds=300)
            if not result.success:
                typer.echo(result.message, err=True)
    except KeyboardInterrupt:
        result = remove_computer_grant(workspace.infrastructure, grant_id=ident)
        typer.echo(result.message)
        if not result.success:
            raise typer.Exit(result.code or 1)
