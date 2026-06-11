from __future__ import annotations

from typing import Optional

import typer

from mlox.application import ProjectApplication
from mlox.cli.common import handle_result
from mlox.cli.context import resolve_credentials
from mlox.cli.rendering.table import render_table

model_app = typer.Typer(help="Manage ML models")


def _parse_model_identifier(model: str) -> tuple[str, str, str]:
    parts = model.split(":")
    if len(parts) != 3:
        typer.echo(
            "[ERROR] Model identifier must be in the format <registry_name>:<model_name>:<version>.",
            err=True,
        )
        raise typer.Exit(code=1)
    return parts[0], parts[1], parts[2]


@model_app.command("list")
def model_list(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    registry: Optional[str] = typer.Option(
        None,
        "--registry",
        "-r",
        help="Name or ID of the model registry service to use.",
    ),
) -> None:
    """List registered models from the configured MLflow registry."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    result = handle_result(
        ProjectApplication.open(resolved_project, resolved_password).list_models(
            registry_name=registry,
        )
    )
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
            f"{model.get('registry_name', '-')}:{model.get('Model', '-')}:{model.get('Version', '-')}",
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


@model_app.command("deploy")
def model_deploy(
    project: Optional[str] = typer.Argument(None, help="Project name"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the session",
        show_default=False,
    ),
    model: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Registered model to deploy with format <registry_name>:<model_name>:<version>",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="Target server IP or hostname where MLServer should run",
    ),
) -> None:
    """Deploy a registered model using the MLflow MLServer docker service."""

    resolved_project, resolved_password = resolve_credentials(project, password)
    registry_name, model_name, model_version = _parse_model_identifier(model)
    result = handle_result(
        ProjectApplication.open(resolved_project, resolved_password).deploy_model(
            registry_name=registry_name,
            model_name=model_name,
            model_version=model_version,
            server_ip=target,
        )
    )
    typer.echo(result.message)
    service = result.data.get("service") if result.data else None
    if service:
        urls = getattr(service, "service_urls", {}) or {}
        ports = getattr(service, "service_ports", {}) or {}
        if urls:
            typer.echo(f"Deployed service URL: {next(iter(urls.values()))}")
        if ports:
            typer.echo(f"Deployed service ports: {ports}")
        typer.echo(f"Model service UUID: {service.uuid}")
        typer.echo(f"Model service name: {service.name}")
