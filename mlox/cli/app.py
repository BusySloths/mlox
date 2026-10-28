"""Root Typer app wiring for the MLOX CLI."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from enum import Enum
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Optional

import typer
import click

from mlox.cli.commands.model import model_app
from mlox.cli.commands.project import project_app
from mlox.cli.commands.server import server_app
from mlox.cli.commands.service import service_app

class JsonErrorsGroup(typer.core.TyperGroup):
    """Render Click parsing errors as JSON when requested at the root."""

    def main(self, args=None, **kwargs):
        arguments = list(sys.argv[1:] if args is None else args)
        json_requested = any(
            arg == "--output=json" or (arg == "--output" and arguments[i + 1:i + 2] == ["json"])
            for i, arg in enumerate(arguments)
        )
        if not json_requested:
            return super().main(args=args, **kwargs)
        kwargs["standalone_mode"] = False
        try:
            result = super().main(args=args, **kwargs)
            if isinstance(result, int) and result:
                raise SystemExit(result)
            return result
        except click.ClickException as exc:
            click.echo(json.dumps({"success": False, "code": exc.exit_code, "message": exc.format_message(), "data": None, "error": "invalid_arguments"}))
            raise SystemExit(exc.exit_code) from exc
        except click.Abort as exc:
            click.echo(json.dumps({"success": False, "code": 1, "message": "Operation aborted.", "data": None, "error": "aborted"}))
            raise SystemExit(1) from exc
        except Exception as exc:
            click.echo(json.dumps({"success": False, "code": 1, "message": f"CLI failed ({type(exc).__name__}).", "data": None, "error": "internal_error"}))
            raise SystemExit(1) from exc


app = typer.Typer(cls=JsonErrorsGroup, help="MLOX command line interface", no_args_is_help=True)

app.add_typer(project_app, name="project")
app.add_typer(server_app, name="server")
app.add_typer(service_app, name="service")
app.add_typer(model_app, name="model")


class OutputFormat(str, Enum):
    human = "human"
    json = "json"


@app.command("schema")
def command_schema() -> None:
    """Describe all CLI commands and their arguments as JSON."""
    from typer.main import get_command

    def describe(command: click.Command, path: list[str]) -> dict:
        parameters = []
        for param in command.params:
            default = param.default
            if callable(default) or not isinstance(default, (str, int, float, bool, list, tuple, type(None))):
                default = None
            parameters.append({
                "name": param.name,
                "kind": "option" if isinstance(param, click.Option) else "argument",
                "flags": list(getattr(param, "opts", [])) + list(getattr(param, "secondary_opts", [])),
                "type": param.type.name,
                "choices": list(param.type.choices) if isinstance(param.type, click.Choice) else None,
                "required": param.required,
                "multiple": bool(getattr(param, "multiple", False)),
                "prompt": bool(getattr(param, "prompt", False)),
                "default": None if "password" in (param.name or "") or "pw" in (param.name or "") else default,
                "help": getattr(param, "help", None),
            })
        result = {"path": path, "help": command.help or command.short_help, "parameters": parameters}
        if isinstance(command, click.Group):
            ctx = click.Context(command)
            result["commands"] = [describe(command.get_command(ctx, name), path + [name]) for name in command.list_commands(ctx)]
        return result

    typer.echo(json.dumps({"schema_version": 1, "cli": describe(get_command(app), ["mlox"])}))


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

    from mlox.cli.common import json_output, handle_result
    from mlox.application.result import OperationResult
    if json_output():
        handle_result(OperationResult(False, 2, "The interactive UI cannot run in JSON mode."))

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@app.command("tui")
def start_tui() -> None:
    """Start the terminal TUI."""

    from mlox.cli.common import json_output, handle_result
    from mlox.application.result import OperationResult
    if json_output():
        handle_result(OperationResult(False, 2, "The interactive TUI cannot run in JSON mode."))

    app_path = Path(__file__).resolve().parents[1] / "tui" / "app.py"
    command = [sys.executable, str(app_path)]
    env = {**os.environ, "MLOX_TUI": "true"}
    result = subprocess.run(command, check=False, env=env)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


@app.callback()
def main(
    ctx: typer.Context,
    output: OutputFormat = typer.Option(OutputFormat.human, "--output", help="Result format."),
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
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env", override=False)
    ctx.ensure_object(dict)["output"] = output.value
    del version


if __name__ == "__main__":
    app()
