"""Generated server command group wiring."""

from __future__ import annotations

import typer

from mlox.cli.generation import register_workspace_commands
from mlox.cli.specifications import SERVER_COMMANDS, SERVER_CONFIG_COMMANDS


server_app = typer.Typer(help="Manage servers in the project infrastructure")
server_configs_app = typer.Typer(help="Server configuration templates")
server_app.add_typer(server_configs_app, name="configs")

GENERATED_SERVER_COMMANDS = register_workspace_commands(server_app, SERVER_COMMANDS)
GENERATED_SERVER_CONFIG_COMMANDS = register_workspace_commands(
    server_configs_app,
    SERVER_CONFIG_COMMANDS,
)
