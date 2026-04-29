"""Root Typer app wiring for the MLOX CLI."""

from __future__ import annotations

import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Optional

import typer

from mlox.cli.commands.model import model_app
from mlox.cli.commands.project import project_app
from mlox.cli.commands.server import server_app
from mlox.cli.commands.service import service_app

app = typer.Typer(help="MLOX command line interface", no_args_is_help=True)

app.add_typer(project_app, name="project")
app.add_typer(server_app, name="server")
app.add_typer(service_app, name="service")
app.add_typer(model_app, name="model")


def _get_package_version() -> str:
    try:
        return importlib_metadata.version("busysloths-mlox")
    except importlib_metadata.PackageNotFoundError:
        return "(local)"
    except Exception:
        return "(unknown)"


def _version_callback(value: Optional[bool]) -> None:
    if value:
        typer.echo(f"MLOX {_get_package_version()}")
        raise typer.Exit()


@app.command("ui")
def start_ui() -> None:
    """Start the Web UI."""

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show MLOX version and exit.",
        callback=_version_callback,
        is_eager=True,
        flag_value=True,
    ),
) -> None:
    del version


if __name__ == "__main__":
    app()
