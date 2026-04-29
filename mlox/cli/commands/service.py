from __future__ import annotations

from typing import List, Optional

import typer

from mlox import operations as ops
from mlox.cli.common import handle_result, parse_kv
from mlox.cli.context import resolve_credentials
from mlox.cli.rendering.table import render_table

service_app = typer.Typer(help="Manage services running on servers")
service_configs_app = typer.Typer(help="Service configuration templates")
service_app.add_typer(service_configs_app, name="configs")


@service_app.command("list")
def service_list(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
) -> None:
    """List services across all servers in the project."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.list_services(project=resolved_project, password=resolved_password)
    )
    services = result.data.get("services", []) if result.data else []
    if not services:
        typer.echo(result.message)
        return

    rows = [
        [
            svc.get("name", "-"),
            svc.get("service_config_id", "-"),
            svc.get("server_ip", "-"),
            svc.get("state", "-"),
            svc.get("labels", []),
            svc.get("ports", []),
            svc.get("urls", []),
        ]
        for svc in services
    ]
    render_table(
        ["Service", "Template", "Server", "State", "Labels", "Ports", "URLs"],
        rows,
        title="Services",
    )


@service_app.command("add")
def service_add(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    server_ip: str = typer.Option(..., help="IP of the target server"),
    template_id: str = typer.Option(..., help="Service template ID"),
    param: List[str] = typer.Option(
        [], "--param", help="Additional template parameter in the form KEY=VALUE"
    ),
) -> None:
    """Add a new service to an existing server."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.add_service(
            project=resolved_project,
            password=resolved_password,
            server_ip=server_ip,
            template_id=template_id,
            params=parse_kv(param),
        )
    )
    typer.echo(result.message)
    service = result.data.get("service") if result.data else None
    if service:
        typer.echo(f"Service UUID: {service.uuid}")
        typer.echo(f"Service Name: {service.name}")


@service_app.command("setup")
def service_setup(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    name: str = typer.Argument(..., help="Service name"),
) -> None:
    """Run the setup routine for a service."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.setup_service(project=resolved_project, password=resolved_password, name=name)
    )
    typer.echo(result.message)
    service = result.data.get("service") if result.data else None
    if service:
        typer.echo(f"Service UUID: {service.uuid}")
        typer.echo(f"Service Name: {service.name}")


@service_app.command("teardown")
def service_teardown(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    name: str = typer.Argument(..., help="Service name"),
) -> None:
    """Remove a service from the infrastructure."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.teardown_service(
            project=resolved_project,
            password=resolved_password,
            name=name,
        )
    )
    typer.echo(result.message)


@service_app.command("logs")
def service_logs(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    name: str = typer.Argument(..., help="Service name"),
    label: Optional[str] = typer.Option(
        None,
        help="Compose service label to fetch logs for",
    ),
    tail: int = typer.Option(200, help="Number of log lines to return"),
) -> None:
    """Show recent logs for a service."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.service_logs(
            project=resolved_project,
            password=resolved_password,
            name=name,
            label=label,
            tail=tail,
        )
    )
    logs = result.data.get("logs", "") if result.data else ""
    typer.echo(logs or result.message)


@service_configs_app.command("list")
def service_configs_list() -> None:
    """List available service configuration templates."""

    result = handle_result(ops.list_service_configs())
    configs = result.data.get("configs", []) if result.data else []
    if not configs:
        typer.echo(result.message)
        return

    rows = [[cfg.get("id", "-"), cfg.get("path", "-")] for cfg in configs]
    render_table(["ID", "Path"], rows, title="Service Configs")
