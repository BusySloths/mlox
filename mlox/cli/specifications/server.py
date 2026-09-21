"""Declarative CLI contract for server workspace operations."""

from __future__ import annotations

from mlox.cli.common import parse_kv
from mlox.cli.generation import CliParameter, WorkspaceCommand
from mlox.cli.rendering.results import (
    config_table_renderer,
    render_message,
    render_server_list,
)


def _server_template_path(value: str) -> str:
    return f"ubuntu/mlox-server.{value}.yaml"


SERVER_COMMANDS = (
    WorkspaceCommand(
        name="list",
        method="list_servers",
        help="List all servers registered in the project infrastructure.",
        renderer=render_server_list,
    ),
    WorkspaceCommand(
        name="add",
        method="add_server",
        help="Register a new server in the current project.",
        parameters=(
            CliParameter(
                "server_template",
                "Server template path relative to the stacks directory",
                target="template_path",
                transform=_server_template_path,
            ),
            CliParameter("ip", "IP or hostname of the server"),
            CliParameter("port", "SSH port of the server", default=22),
            CliParameter("root_user", "Initial root user", default="root"),
            CliParameter(
                "root_pw",
                "Root password",
                target="root_password",
                prompt=True,
                hide_input=True,
                show_default=False,
            ),
            CliParameter(
                "param",
                "Additional template parameter in the form KEY=VALUE",
                target="extra_params",
                declarations=("--param",),
                annotation=list[str],
                default=[],
                transform=parse_kv,
            ),
        ),
        renderer=render_message,
    ),
    WorkspaceCommand(
        name="setup",
        method="setup_server",
        help="Run the setup routine on a server.",
        parameters=(
            CliParameter("ip", "Server IP or hostname", kind="argument"),
        ),
        renderer=render_message,
    ),
    WorkspaceCommand(
        name="teardown",
        method="teardown_server",
        help="Tear down a server and remove it from the infrastructure.",
        parameters=(
            CliParameter("ip", "Server IP or hostname", kind="argument"),
        ),
        renderer=render_message,
    ),
    WorkspaceCommand(
        name="save-key",
        method="save_server_key",
        help="Save a server key file for local access.",
        parameters=(
            CliParameter("ip", "Server IP or hostname", kind="argument"),
            CliParameter(
                "output",
                "Path to store the encrypted key file",
                target="output_path",
            ),
        ),
        renderer=render_message,
    ),
)


SERVER_CONFIG_COMMANDS = (
    WorkspaceCommand(
        name="list",
        method="list_server_configs",
        help="List available server configuration templates.",
        renderer=config_table_renderer("Server Configs"),
        scope="class",
    ),
)
