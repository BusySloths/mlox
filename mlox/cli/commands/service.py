"""Generated service command group wiring."""

from __future__ import annotations

import typer

from mlox.cli.generation import register_workspace_commands
from mlox.cli.specifications.service import SERVICE_COMMANDS, SERVICE_CONFIG_COMMANDS


service_app = typer.Typer(help="Manage services running on servers")
service_configs_app = typer.Typer(help="Service configuration templates")
service_app.add_typer(service_configs_app, name="configs")

GENERATED_SERVICE_COMMANDS = register_workspace_commands(service_app, SERVICE_COMMANDS)
GENERATED_SERVICE_CONFIG_COMMANDS = register_workspace_commands(
    service_configs_app,
    SERVICE_CONFIG_COMMANDS,
)
