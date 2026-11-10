from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from mlox.project import ProjectWorkspace, resolve_project_path
from mlox.cli.common import handle_result
from mlox.cli.context import PASSWORD_ENVVAR, PROJECT_ENVVAR, resolve_password, resolve_project
from mlox.application.result import OperationResult
from mlox.cli.generation import WorkspaceCommand, register_workspace_commands
from mlox.cli.rendering.results import render_inspection

project_app = typer.Typer(help="Manage MLOX projects")
register_workspace_commands(project_app, (
    WorkspaceCommand(name="inspect", method="inspect_project", help="Inspect the active project.", renderer=render_inspection),
))


def _managed_transfer_server(path: Path, password: str, identifier: str):
    """Resolve a server registered in the local project."""
    from mlox.project.repository import SqlCipherRepository

    infra = SqlCipherRepository(path, password).load().infrastructure
    bundle = infra.get_bundle_by_ip(identifier)
    if bundle is not None:
        return bundle.server
    candidates = [item for item in infra.bundles if item.name == identifier or item.server.ip.endswith(identifier)]
    if len(candidates) > 1:
        raise ValueError(f"Server identifier {identifier!r} is ambiguous")
    raise ValueError(f"Server {identifier!r} is not registered in the local project")


def _project_password(path: Path, explicit: Optional[str] = None) -> str:
    from mlox.application.use_cases.project import project_password_env_name

    specific = os.getenv(project_password_env_name(path.stem))
    return resolve_password(explicit or specific, prompt_text=f"Password for project {path.stem}")


@project_app.command("new")
def project_new(
    name: str = typer.Argument(..., help="Project file (the .mlox suffix is optional)"),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        help="Password for the project",
        show_default=False,
    ),
) -> None:
    resolved_password = resolve_password(password)
    try:
        workspace = ProjectWorkspace.create(name, resolved_password)
    except Exception as exc:
        handle_result(OperationResult(False, 1, f"Failed to create project: {exc}"))
        return
    result = handle_result(workspace.project_created())
    typer.echo(result.message)
    typer.echo("")
    typer.echo("Run the following to export the project credentials:")
    typer.echo(f"  export {PROJECT_ENVVAR}='{resolve_project_path(name)}'")
    typer.echo(f"  export {PASSWORD_ENVVAR}='<your-project-password>'")


@project_app.command("push")
def project_push(
    ip: str = typer.Option(..., "--ip", help="Registered server address, bundle name or unique address suffix"),
    name: Optional[str] = typer.Option(None, "--name", help="Project name; defaults to the current project"),
    project: Optional[str] = typer.Option(None, "--project", help="Local project path; useful when the local filename differs from --name"),
    password: Optional[str] = typer.Option(None, "--password", help="Password for the current project containing the server", show_default=False),
    force: bool = typer.Option(False, "--force", help="Replace an existing registry file"),
) -> None:
    """Publish an encrypted project snapshot to the SSH server."""
    from mlox.project.transfer import project_name, push_project

    try:
        current = resolve_project_path(resolve_project(None))
        source = resolve_project_path(project or name) if project or name else current
        registry_name = project_name(name if name else source.name)
        server = _managed_transfer_server(current, _project_password(current, password), ip)
        data = push_project(registry_name, source, server=server, force=force)
        result = OperationResult(True, 0, f"Pushed project {registry_name} to {ip} ({data['size_bytes'] / 1_000_000:.2f} MB).", data)
    except Exception as exc:
        result = OperationResult(False, 1, f"Could not push project: {exc}")
    result = handle_result(result)
    typer.echo(result.message)


@project_app.command("pull")
def project_pull(
    ip: str = typer.Option(..., "--ip", help="Registered server address, bundle name or unique address suffix"),
    name: Optional[str] = typer.Option(None, "--name", help="Project name; defaults to the current project"),
    project: Optional[str] = typer.Option(None, "--project", help="Local project containing a managed server"),
    password: Optional[str] = typer.Option(None, "--password", help="Password for the local project", show_default=False),
) -> None:
    """Download an encrypted project without replacing existing local files."""
    from mlox.project.transfer import project_name, pull_project

    try:
        current = project or resolve_project(None)
        selected = name if name else Path(current).name
        registry_name = project_name(selected)
        current_path = resolve_project_path(current)
        project_password = _project_password(current_path, password)
        server = _managed_transfer_server(current_path, project_password, ip)
        data = pull_project(registry_name, server=server)
        result = OperationResult(True, 0, f"Pulled project to {data['path']} ({data['size_bytes'] / 1_000_000:.2f} MB).", data)
    except Exception as exc:
        result = OperationResult(False, 1, f"Could not pull project: {exc}")
    result = handle_result(result)
    typer.echo(result.message)
