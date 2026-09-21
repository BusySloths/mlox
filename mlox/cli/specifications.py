"""Explicit allowlist of ProjectWorkspace methods exposed through the CLI."""

from __future__ import annotations

from mlox.cli.common import parse_kv
from mlox.cli.generation import CliParameter, WorkspaceCommand
from mlox.cli.rendering.results import (
    config_table_renderer,
    render_message,
    render_models,
    render_server_list,
    render_service_identity,
    render_service_list,
    render_service_logs,
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


SERVICE_COMMANDS = (
    WorkspaceCommand(
        name="list",
        method="list_services",
        help="List services across all servers in the project.",
        renderer=render_service_list,
    ),
    WorkspaceCommand(
        name="add",
        method="add_service",
        help="Add a new service to an existing server.",
        parameters=(
            CliParameter("server_ip", "IP of the target server"),
            CliParameter("template_id", "Service template ID"),
            CliParameter(
                "param",
                "Additional template parameter in the form KEY=VALUE",
                target="params",
                declarations=("--param",),
                annotation=list[str],
                default=[],
                transform=parse_kv,
            ),
        ),
        renderer=render_service_identity,
    ),
    WorkspaceCommand(
        name="setup",
        method="setup_service",
        help="Run the setup routine for a service.",
        parameters=(CliParameter("name", "Service name", kind="argument"),),
        renderer=render_service_identity,
    ),
    WorkspaceCommand(
        name="teardown",
        method="teardown_service",
        help="Remove a service from the infrastructure.",
        parameters=(CliParameter("name", "Service name", kind="argument"),),
        renderer=render_message,
    ),
    WorkspaceCommand(
        name="logs",
        method="service_logs",
        help="Show recent logs for a service.",
        parameters=(
            CliParameter("name", "Service name", kind="argument"),
            CliParameter("label", "Service log label to fetch logs for"),
            CliParameter("tail", "Number of log lines to return"),
        ),
        renderer=render_service_logs,
    ),
)


SERVICE_CONFIG_COMMANDS = (
    WorkspaceCommand(
        name="list",
        method="list_service_configs",
        help="List available service configuration templates.",
        renderer=config_table_renderer("Service Configs"),
        scope="class",
    ),
)


MODEL_COMMANDS = (
    WorkspaceCommand(
        name="list",
        method="list_models",
        help="List registered models from the configured MLflow registry.",
        parameters=(
            CliParameter(
                "registry",
                "Name or ID of the model registry service to use.",
                target="registry_name",
                declarations=("--registry", "-r"),
            ),
        ),
        renderer=render_models,
    ),
)
