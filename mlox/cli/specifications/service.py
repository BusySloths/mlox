"""Declarative CLI contract for service workspace operations."""

from __future__ import annotations

from mlox.cli.common import parse_kv
from mlox.cli.generation import CliParameter, WorkspaceCommand
from mlox.cli.rendering.results import (
    config_table_renderer,
    render_message,
    render_service_identity,
    render_service_list,
    render_service_logs,
    render_inspection,
)


SERVICE_COMMANDS = (
    WorkspaceCommand(name="proxy-routes", method="list_proxy_routes", help="List routes on a Docker reverse proxy.",
        parameters=(CliParameter("name", "Proxy service name"),), renderer=render_inspection),
    WorkspaceCommand(name="proxy-route-add", method="add_proxy_route", help="Add a live route to a Docker reverse proxy.",
        parameters=(CliParameter("name", "Proxy service name"), CliParameter("hostname", "Public hostname"),
                    CliParameter("backend", "Backend URL; omitted to use the selected app endpoint"),
                    CliParameter("tls_mode", "Public TLS: self-signed, letsencrypt, or managed"),
                    CliParameter("insecure_backend", "Disable backend TLS certificate verification"),
                    CliParameter("backend_host", "Optional backend Host header"),
                    CliParameter("service_uuid", "Optional UUID of the relayed mlox service"),
                    CliParameter("tls_secret_manager_uuid", "Managed certificate secret-manager UUID"),
                    CliParameter("tls_secret_name", "Managed certificate secret name")), renderer=render_message),
    WorkspaceCommand(name="proxy-route-remove", method="remove_proxy_route", help="Remove a live proxy route.",
        parameters=(CliParameter("name", "Proxy service name"), CliParameter("hostname", "Public hostname")), renderer=render_message),
    WorkspaceCommand(name="inspect", method="inspect_service", help="Inspect a service by UUID or name.",
        parameters=(CliParameter("identifier", "Service UUID or name", kind="argument"),), renderer=render_inspection),
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
            CliParameter("server_ip", "Server IP, unique IP suffix, or bundle name"),
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
            CliParameter("name", "Service UUID or name", kind="argument"),
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
