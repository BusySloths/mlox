from __future__ import annotations

from typing import List, Optional

import typer

from mlox import operations as ops
from mlox.cli.common import handle_result, parse_kv
from mlox.cli.context import resolve_credentials
from mlox.cli.rendering.table import render_table

server_app = typer.Typer(help="Manage servers in the project infrastructure")
server_configs_app = typer.Typer(help="Server configuration templates")
server_app.add_typer(server_configs_app, name="configs")


@server_app.command("list")
def server_list(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
) -> None:
    """List all servers registered in the project infrastructure."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.list_servers(project=resolved_project, password=resolved_password)
    )
    servers = result.data.get("servers", []) if result.data else []
    if not servers:
        typer.echo(result.message)
        return

    rows = [
        [
            server.get("ip", "-"),
            server.get("state", "-"),
            server.get("service_count", 0),
            server.get("service_config_id") or server.get("template", "-"),
            server.get("port", "-"),
            server.get("discovered", "-"),
            server.get("backend", []),
        ]
        for server in servers
    ]
    render_table(
        ["IP", "State", "#Services", "Template", "Port", "Discovered", "Backend"],
        rows,
        title="Servers",
    )


@server_app.command("add")
def server_add(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
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
) -> None:
    """Register a new server in the current project."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.add_server(
            project=resolved_project,
            password=resolved_password,
            template_path=f"ubuntu/mlox-server.{server_template}.yaml",
            ip=ip,
            port=port,
            root_user=root_user,
            root_password=root_pw,
            extra_params=parse_kv(param),
        )
    )
    typer.echo(result.message)


@server_app.command("setup")
def server_setup(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    ip: str = typer.Argument(..., help="Server IP or hostname"),
) -> None:
    """Run the setup routine on a server."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.setup_server(project=resolved_project, password=resolved_password, ip=ip)
    )
    typer.echo(result.message)


@server_app.command("teardown")
def server_teardown(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    ip: str = typer.Argument(..., help="Server IP or hostname"),
) -> None:
    """Tear down a server and remove it from the infrastructure."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.teardown_server(project=resolved_project, password=resolved_password, ip=ip)
    )
    typer.echo(result.message)


@server_app.command("save-key")
def server_save_key(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    ip: str = typer.Argument(..., help="Server IP or hostname"),
    output: str = typer.Option(..., help="Path to store the encrypted key file"),
) -> None:
    """Save a server key file for local access."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ops.save_server_key(
            project=resolved_project,
            password=resolved_password,
            ip=ip,
            output_path=output,
        )
    )
    typer.echo(result.message)


@server_configs_app.command("list")
def server_configs_list() -> None:
    """List available server configuration templates."""

    result = handle_result(ops.list_server_configs())
    configs = result.data.get("configs", []) if result.data else []
    if not configs:
        typer.echo(result.message)
        return

    rows = [[cfg.get("id", "-"), cfg.get("path", "-")] for cfg in configs]
    render_table(["ID", "Path"], rows, title="Server Configs")
