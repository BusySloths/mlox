"""Command line interface for MLOX.

This rewrite exposes a higher level interface for managing projects,
servers and services in preparation for a server/client architecture.
"""

from __future__ import annotations

import logging
import os
import shutil
import textwrap
from typing import Any, Dict, List, Optional, Sequence, Tuple

import typer

from mlox import operations as ops
from mlox.operations import OperationResult

logger = logging.getLogger(__name__)

PROJECT_ENVVAR = "MLOX_PROJECT_NAME"
PASSWORD_ENVVAR = "MLOX_PROJECT_PASSWORD"


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


def _resolve_project(raw: Optional[str]) -> str:
    """Return the project name from CLI input or environment."""

    if raw:
        return raw
    env_value = os.getenv(PROJECT_ENVVAR)
    if env_value:
        return env_value
    raise typer.BadParameter(
        f"Provide a project name or set {PROJECT_ENVVAR}.", param_hint="project"
    )


def _resolve_password(
    raw: Optional[str], prompt_text: str = "Password for the session"
) -> str:
    """Return the password from CLI input or environment, prompting if needed."""

    if raw:
        return raw
    env_value = os.getenv(PASSWORD_ENVVAR)
    if env_value:
        return env_value
    return typer.prompt(prompt_text, hide_input=True)


def _resolve_credentials(
    project: Optional[str],
    password: Optional[str],
    prompt_text: str = "Password for the session",
) -> Tuple[str, str]:
    """Resolve CLI credentials from flags or environment variables."""

    resolved_project = _resolve_project(project)
    resolved_password = _resolve_password(password, prompt_text=prompt_text)
    return resolved_project, resolved_password


def _stringify_value(value: Any) -> str:
    """Return a human readable string for table cells."""

    if value is None:
        return "-"
    if isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value if item is not None and item != ""]
        return ", ".join(parts) if parts else "-"
    if isinstance(value, dict):
        if not value:
            return "-"
        return ", ".join(f"{key}={val}" for key, val in value.items())
    text = str(value)
    return text if text.strip() else "-"


def _wrap_cell(text: str, width: int) -> List[str]:
    """Wrap a cell into multiple lines respecting the target width."""

    width = max(width, 8)
    lines: List[str] = []
    for raw_line in text.splitlines() or [""]:
        wrapped = textwrap.wrap(
            raw_line,
            width=width,
            drop_whitespace=False,
            break_long_words=True,
            break_on_hyphens=False,
        )
        if not wrapped:
            lines.append("")
        else:
            lines.extend(wrapped)
    return lines or [""]


def _format_table_lines(
    headers: Sequence[str], rows: Sequence[Sequence[Any]]
) -> List[str]:
    """Return formatted ASCII table lines."""

    if not headers:
        return []
    term_width = shutil.get_terminal_size((100, 20)).columns
    per_column_cap = max(16, min(48, max((term_width - 6) // len(headers), 16)))

    string_rows: List[List[str]] = [
        [_stringify_value(cell) for cell in row] for row in rows
    ]

    col_widths = [len(h) for h in headers]
    prepared_cells: List[List[List[str]]] = []

    for row in string_rows:
        row_cells: List[List[str]] = []
        for idx, header in enumerate(headers):
            cell_value = row[idx] if idx < len(row) else "-"
            cell_lines = _wrap_cell(cell_value, per_column_cap)
            row_cells.append(cell_lines)
            longest_line = max(len(line) for line in cell_lines) if cell_lines else 0
            col_widths[idx] = min(per_column_cap, max(col_widths[idx], longest_line))
        prepared_cells.append(row_cells)

    # Ensure headers respect the maximum width
    for idx, header in enumerate(headers):
        wrapped_header = _wrap_cell(header, per_column_cap)
        header_width = max(len(line) for line in wrapped_header)
        col_widths[idx] = min(per_column_cap, max(col_widths[idx], header_width))

    def make_border(char: str = "-") -> str:
        parts = ["+"]
        for width in col_widths:
            parts.append(char * (width + 2))
            parts.append("+")
        return "".join(parts)

    def make_row(line_parts: Sequence[str]) -> str:
        padded = [part.ljust(width) for part, width in zip(line_parts, col_widths)]
        return "| " + " | ".join(padded) + " |"

    top_border = make_border("-")
    separator_border = make_border("=")
    rows_border = make_border("-")

    table_lines: List[str] = [top_border]
    header_cell_lines = [
        _wrap_cell(header, col_widths[idx]) for idx, header in enumerate(headers)
    ]
    header_height = max(len(cell) for cell in header_cell_lines)
    for line_index in range(header_height):
        parts = [
            header_cell_lines[idx][line_index]
            if line_index < len(header_cell_lines[idx])
            else ""
            for idx in range(len(headers))
        ]
        table_lines.append(make_row(parts))
    table_lines.append(separator_border)

    if not prepared_cells:
        table_lines.append(make_row(["-"] * len(headers)))
        table_lines.append(rows_border)
        return table_lines

    for row_cells in prepared_cells:
        row_height = max(len(cell) for cell in row_cells)
        for line_index in range(row_height):
            parts = [
                row_cells[idx][line_index] if line_index < len(row_cells[idx]) else ""
                for idx in range(len(headers))
            ]
            table_lines.append(make_row(parts))
        table_lines.append(rows_border)
    return table_lines


def render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    title: Optional[str] = None,
) -> None:
    """Render a styled table to the terminal."""

    lines = _format_table_lines(headers, rows)
    if not lines:
        return
    if title:
        typer.echo(typer.style(title, fg=typer.colors.BRIGHT_BLUE, bold=True))
    header_end = 0
    for idx, line in enumerate(lines):
        if "=" in line and set(line.strip()) <= {"+", "="}:
            header_end = idx
            break
    for idx, line in enumerate(lines):
        if 0 < idx < header_end:
            typer.echo(typer.style(line, bold=True))
        else:
            typer.echo(line)


# ---------------------------------------------------------------------------
# Project commands
# ---------------------------------------------------------------------------


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
):
    resolved_password = _resolve_password(password)
    result = _handle_result(ops.create_project(name=name, password=resolved_password))
    typer.echo(result.message)
    typer.echo("")
    typer.echo("Run the following to export the project credentials:")
    typer.echo(f"  export {PROJECT_ENVVAR}='{name}'")
    typer.echo(f"  export {PASSWORD_ENVVAR}='{resolved_password}'")


# ---------------------------------------------------------------------------
# Server commands
# ---------------------------------------------------------------------------


@server_app.command("list")
def server_list(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
):
    """List all servers registered in the project infrastructure."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
        ops.list_servers(project=resolved_project, password=resolved_password)
    )
    servers = []
    if result.data:
        servers = result.data.get("servers", [])
    if not servers:
        typer.echo(result.message)
        return
    rows = []
    for server in servers:
        rows.append(
            [
                server.get("ip", "-"),
                server.get("state", "-"),
                server.get("service_count", 0),
                server.get("service_config_id") or server.get("template", "-"),
                server.get("port", "-"),
                server.get("discovered", "-"),
                server.get("backend", []),
            ]
        )
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
):
    """Register a new server in the current project."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    params = parse_kv(param)
    template_path = f"ubuntu/mlox-server.{server_template}.yaml"
    result = _handle_result(
        ops.add_server(
            project=resolved_project,
            password=resolved_password,
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
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    ip: str = typer.Argument(..., help="Server IP or hostname"),
):
    """Run the setup routine on a server."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
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
):
    """Tear down a server and remove it from the infrastructure."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
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
    output: str = typer.Option(
        ...,
        help="Path to store the encrypted key file",
    ),
):
    """Save a server key file for local access."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
        ops.save_server_key(
            project=resolved_project,
            password=resolved_password,
            ip=ip,
            output_path=output,
        )
    )
    typer.echo(result.message)


# ---------------------------------------------------------------------------
# Service commands
# ---------------------------------------------------------------------------


@service_app.command("list")
def service_list(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
):
    """List services across all servers in the project."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
        ops.list_services(project=resolved_project, password=resolved_password)
    )
    services = []
    if result.data:
        services = result.data.get("services", [])
    if not services:
        typer.echo(result.message)
        return
    rows = []
    for svc in services:
        rows.append(
            [
                svc.get("name", "-"),
                svc.get("service_config_id", "-"),
                svc.get("server_ip", "-"),
                svc.get("state", "-"),
                svc.get("labels", []),
                svc.get("ports", []),
                svc.get("urls", []),
            ]
        )
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
):
    """Add a new service to an existing server."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    params = parse_kv(param)
    result = _handle_result(
        ops.add_service(
            project=resolved_project,
            password=resolved_password,
            server_ip=server_ip,
            template_id=template_id,
            params=params,
        )
    )
    typer.echo(result.message)


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
):
    """Run the setup routine for a service."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
        ops.setup_service(
            project=resolved_project, password=resolved_password, name=name
        )
    )
    typer.echo(result.message)


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
):
    """Remove a service from the infrastructure."""

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
        ops.teardown_service(
            project=resolved_project, password=resolved_password, name=name
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
    label: str = typer.Option(None, help="Compose service label to fetch logs for"),
    tail: int = typer.Option(200, help="Number of log lines to return"),
):
    """Show recent logs for a service (compose service label).

    If `label` is not provided the command will attempt to use the service's
    default compose service mapping.
    """

    resolved_project, resolved_password = _resolve_credentials(project, password)
    result = _handle_result(
        ops.service_logs(
            project=resolved_project,
            password=resolved_password,
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
    rows = [[cfg.get("id", "-"), cfg.get("path", "-")] for cfg in configs]
    render_table(["ID", "Path"], rows, title="Server Configs")


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
    rows = [[cfg.get("id", "-"), cfg.get("path", "-")] for cfg in configs]
    render_table(["ID", "Path"], rows, title="Service Configs")


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app()
