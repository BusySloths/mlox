"""Result renderers used by generated CLI workspace commands."""

from __future__ import annotations

from typing import Any, Callable

import typer

from mlox.application.result import OperationResult
from mlox.cli.rendering.table import render_table


def render_message(result: OperationResult[Any]) -> None:
    """Render the operation message."""

    typer.echo(result.message)


def render_server_list(result: OperationResult[Any]) -> None:
    """Render the server list payload as a table."""

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


def render_service_list(result: OperationResult[Any]) -> None:
    """Render the service list payload as a table."""

    services = result.data.get("services", []) if result.data else []
    if not services:
        typer.echo(result.message)
        return
    rows = [
        [
            service.get("name", "-"),
            service.get("service_config_id", "-"),
            service.get("server_ip", "-"),
            service.get("state", "-"),
            service.get("labels", []),
            service.get("ports", []),
            service.get("urls", []),
        ]
        for service in services
    ]
    render_table(
        ["Service", "Template", "Server", "State", "Labels", "Ports", "URLs"],
        rows,
        title="Services",
    )


def render_service_identity(result: OperationResult[Any]) -> None:
    """Render a message followed by the affected service identity."""

    typer.echo(result.message)
    service = result.data.get("service") if result.data else None
    if service:
        typer.echo(f"Service UUID: {service.uuid}")
        typer.echo(f"Service Name: {service.name}")


def render_service_logs(result: OperationResult[Any]) -> None:
    """Render service log text, falling back to the result message."""

    logs = result.data.get("logs", "") if result.data else ""
    typer.echo(logs or result.message)


def config_table_renderer(title: str) -> Callable[[OperationResult[Any]], None]:
    """Build a renderer for server or service configuration rows."""

    def render_configs(result: OperationResult[Any]) -> None:
        configs = result.data.get("configs", []) if result.data else []
        if not configs:
            typer.echo(result.message)
            return
        rows = [[config.get("id", "-"), config.get("path", "-")] for config in configs]
        render_table(["ID", "Path"], rows, title=title)

    return render_configs


def render_models(result: OperationResult[Any]) -> None:
    """Render the registered-model payload as a table."""

    models = result.data.get("models", []) if result.data else []
    if not models:
        typer.echo(result.message)
        return
    rows = [
        [
            model.get("registry_name", "-"),
            "x" if model.get("is_deployed", False) else "-",
            model.get("Model", "-"),
            model.get("Stage", "-"),
            model.get("Version", "-"),
            model.get("Description", "-"),
            (
                f"{model.get('registry_name', '-')}:"
                f"{model.get('Model', '-')}:"
                f"{model.get('Version', '-')}"
            ),
        ]
        for model in models
    ]
    render_table(
        [
            "Registry",
            "Deployed",
            "Model",
            "Stage",
            "Version",
            "Description",
            "Deploy Key",
        ],
        rows,
        title="Models",
    )
