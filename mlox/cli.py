"""Command line interface for MLOX.

This rewrite exposes a higher level interface for managing projects,
servers and services in preparation for a server/client architecture.
"""

from __future__ import annotations

import logging
from typing import Dict, List

import typer

from mlox import operations as ops
from mlox.operations import OperationResult


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


app = typer.Typer(help="MLOX command line interface", no_args_is_help=True)

project_app = typer.Typer(help="Manage MLOX projects")
server_app = typer.Typer(help="Manage servers in the project infrastructure")
service_app = typer.Typer(help="Manage services running on servers")

# New nested groups for configs under server and service
server_configs_app = typer.Typer(help="Server configuration templates")
service_configs_app = typer.Typer(help="Service configuration templates")

app.add_typer(project_app, name="project")
app.add_typer(server_app, name="server")
app.add_typer(service_app, name="service")

# Attach configs namespace under existing groups
server_app.add_typer(server_configs_app, name="configs")
service_app.add_typer(service_configs_app, name="configs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _handle_result(result: OperationResult) -> OperationResult:
    """Raise a ``typer.Exit`` when an operation fails."""

    if not result.success:
        typer.echo(f"[ERROR] {result.message}", err=True)
        raise typer.Exit(code=result.code)
    return result


def parse_kv(pairs: List[str]) -> Dict[str, str]:
    """Convert a list of ``KEY=VALUE`` strings into a dictionary."""

    data: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        data[key] = value
    return data


# ---------------------------------------------------------------------------
# Project commands
# ---------------------------------------------------------------------------


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
):
    result = _handle_result(ops.create_project(name=name, password=password))
    typer.echo(result.message)


# ---------------------------------------------------------------------------
# Server commands
# ---------------------------------------------------------------------------


@server_app.command("list")
def server_list(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
):
    """List all servers registered in the project infrastructure."""

    result = _handle_result(ops.list_servers(project=project, password=password))
    servers = []
    if result.data:
        servers = result.data.get("servers", [])
    if not servers:
        typer.echo(result.message)
        return

    for server in servers:
        typer.echo(
            f"{server['ip']} ({server['state']}) - {server['service_count']} services"
        )


@server_app.command("add")
def server_add(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    server_template: str = typer.Option(
        ..., help="Server template path relative to the stacks directory"
    ),
    ip: str = typer.Option(..., help="IP or hostname of the server"),
    port: int = typer.Option(22, help="SSH port of the server"),
    root_user: str = typer.Option("root", help="Initial root user"),
    root_pw: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Root password"
    ),
    param: List[str] = typer.Option(
        [], "--param", help="Additional template parameter in the form KEY=VALUE"
    ),
):
    """Register a new server in the current project."""

    params = parse_kv(param)
    template_path = f"ubuntu/mlox-server.{server_template}.yaml"
    result = _handle_result(
        ops.add_server(
            project=project,
            password=password,
            template_path=template_path,
            ip=ip,
            port=port,
            root_user=root_user,
            root_password=root_pw,
            extra_params=params,
        )
    )
    typer.echo(result.message)


@server_app.command("setup")
def server_setup(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    ip: str = typer.Argument(..., help="Server IP or hostname"),
):
    """Run the setup routine on a server."""

    result = _handle_result(ops.setup_server(project=project, password=password, ip=ip))
    typer.echo(result.message)


@server_app.command("teardown")
def server_teardown(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    ip: str = typer.Argument(..., help="Server IP or hostname"),
):
    """Tear down a server and remove it from the infrastructure."""

    result = _handle_result(
        ops.teardown_server(project=project, password=password, ip=ip)
    )
    typer.echo(result.message)


@server_app.command("save-key")
def server_save_key(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    ip: str = typer.Argument(..., help="Server IP or hostname"),
    output: str = typer.Option(
        ...,
        help="Path to store the encrypted key file",
    ),
):
    """Save a server key file for local access."""

    result = _handle_result(
        ops.save_server_key(project=project, password=password, ip=ip, output_path=output)
    )
    typer.echo(result.message)


# ---------------------------------------------------------------------------
# Service commands
# ---------------------------------------------------------------------------


@service_app.command("list")
def service_list(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
):
    """List services across all servers in the project."""

    result = _handle_result(ops.list_services(project=project, password=password))
    services = []
    if result.data:
        services = result.data.get("services", [])
    if not services:
        typer.echo(result.message)
        return

    for svc in services:
        typer.echo(
            f"{svc['name']} ({svc['service_config_id']}) on {svc['server_ip']}"
        )


@service_app.command("add")
def service_add(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    server_ip: str = typer.Option(..., help="IP of the target server"),
    template_id: str = typer.Option(..., help="Service template ID"),
    param: List[str] = typer.Option(
        [], "--param", help="Additional template parameter in the form KEY=VALUE"
    ),
):
    """Add a new service to an existing server."""

    params = parse_kv(param)
    result = _handle_result(
        ops.add_service(
            project=project,
            password=password,
            server_ip=server_ip,
            template_id=template_id,
            params=params,
        )
    )
    typer.echo(result.message)


@service_app.command("setup")
def service_setup(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    name: str = typer.Argument(..., help="Service name"),
):
    """Run the setup routine for a service."""

    result = _handle_result(
        ops.setup_service(project=project, password=password, name=name)
    )
    typer.echo(result.message)


@service_app.command("teardown")
def service_teardown(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    name: str = typer.Argument(..., help="Service name"),
):
    """Remove a service from the infrastructure."""

    result = _handle_result(
        ops.teardown_service(project=project, password=password, name=name)
    )
    typer.echo(result.message)


@service_app.command("logs")
def service_logs(
    project: str = typer.Argument(..., help="Project name"),
    password: str = typer.Option(
        ..., prompt=True, hide_input=True, help="Password for the session"
    ),
    name: str = typer.Argument(..., help="Service name"),
    label: str = typer.Option(None, help="Compose service label to fetch logs for"),
    tail: int = typer.Option(200, help="Number of log lines to return"),
):
    """Show recent logs for a service (compose service label).

    If `label` is not provided the command will attempt to use the service's
    default compose service mapping.
    """

    result = _handle_result(
        ops.service_logs(
            project=project,
            password=password,
            name=name,
            label=label,
            tail=tail,
        )
    )
    logs = ""
    if result.data:
        logs = result.data.get("logs", "")
    if logs:
        typer.echo(logs)
    else:
        typer.echo(result.message)


# ---------------------------------------------------------------------------
# Configs commands (nested under server and service)
# ---------------------------------------------------------------------------


@server_configs_app.command("list")
def server_configs_list():
    """List available server configuration templates."""

    result = _handle_result(ops.list_server_configs())
    configs = []
    if result.data:
        configs = result.data.get("configs", [])
    if not configs:
        typer.echo(result.message)
        return
    for cfg in configs:
        typer.echo(f"{cfg['id']} - {cfg['path']}")


@service_configs_app.command("list")
def service_configs_list():
    """List available service configuration templates."""

    result = _handle_result(ops.list_service_configs())
    configs = []
    if result.data:
        configs = result.data.get("configs", [])
    if not configs:
        typer.echo(result.message)
        return
    for cfg in configs:
        typer.echo(f"{cfg['id']} - {cfg['path']}")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app()
