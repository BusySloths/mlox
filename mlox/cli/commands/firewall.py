"""First-class project firewall commands."""

from __future__ import annotations

import time
import typer

from mlox.cli.generation import register_workspace_commands
from mlox.cli.specifications.firewall import FIREWALL_ACCESS_COMMANDS, FIREWALL_RULE_COMMANDS


class OrderedFirewallGroup(typer.core.TyperGroup):
    """Keep firewall help in the same order as the workflow users follow."""

    def list_commands(self, ctx):
        return list(self.commands)


firewall_app = typer.Typer(
    cls=OrderedFirewallGroup,
    help="Manage project firewall rules and temporary access",
)
GENERATED_FIREWALL_COMMANDS = register_workspace_commands(firewall_app, FIREWALL_ACCESS_COMMANDS)


@firewall_app.command("access-hold")
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
        raise typer.BadParameter("The hold command is interactive; use firewall access-add for JSON output.")
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


GENERATED_FIREWALL_COMMANDS.update(
    register_workspace_commands(firewall_app, FIREWALL_RULE_COMMANDS)
)
