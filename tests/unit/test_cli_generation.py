import inspect

import pytest
import typer

from mlox.cli.commands import model, server, service
from mlox.cli.generation import (
    CliParameter,
    WorkspaceCommand,
    build_workspace_command,
    register_workspace_commands,
    validate_workspace_command,
)
from mlox.cli.rendering.results import render_message
from mlox.cli.specifications import SERVER_COMMANDS


def _server_command(name: str) -> WorkspaceCommand:
    return next(spec for spec in SERVER_COMMANDS if spec.name == name)


def test_generated_signature_infers_workspace_types_and_defaults():
    callback = build_workspace_command(_server_command("add"))

    signature = inspect.signature(callback)

    assert list(signature.parameters) == [
        "project",
        "password",
        "server_template",
        "ip",
        "port",
        "root_user",
        "root_pw",
        "param",
    ]
    assert signature.parameters["port"].annotation is int
    assert signature.parameters["port"].default.default == 22
    assert signature.parameters["root_user"].default.default == "root"
    assert signature.parameters["root_pw"].default.prompt is True
    assert signature.parameters["root_pw"].default.hide_input is True
    assert signature.parameters["param"].annotation == list[str]


def test_manifest_rejects_unknown_workspace_method():
    spec = WorkspaceCommand(
        name="broken",
        method="missing_method",
        help="Broken command",
        renderer=render_message,
    )

    with pytest.raises(ValueError, match="unknown ProjectWorkspace method"):
        validate_workspace_command(spec)


def test_manifest_rejects_missing_required_workspace_parameter():
    spec = WorkspaceCommand(
        name="setup",
        method="setup_server",
        help="Broken setup command",
        renderer=render_message,
    )

    with pytest.raises(ValueError, match="required workspace parameter.*ip"):
        validate_workspace_command(spec)


def test_manifest_rejects_method_without_operation_result():
    spec = WorkspaceCommand(
        name="entries",
        method="list_entries",
        help="Broken entries command",
        renderer=render_message,
    )

    with pytest.raises(ValueError, match="to return OperationResult"):
        validate_workspace_command(spec)


def test_generator_rejects_unsupported_cli_annotation():
    spec = WorkspaceCommand(
        name="setup",
        method="setup_server",
        help="Broken setup command",
        renderer=render_message,
        parameters=(
            CliParameter("ip", "Server IP", annotation=dict[str, str]),
        ),
    )

    with pytest.raises(ValueError, match="unsupported annotation"):
        build_workspace_command(spec)


def test_registration_rejects_duplicate_command_names():
    app = typer.Typer()
    command = _server_command("list")

    with pytest.raises(ValueError, match="Duplicate CLI command name 'list'"):
        register_workspace_commands(app, (command, command))


def test_simple_commands_are_generated_but_model_deploy_stays_explicit():
    assert set(server.GENERATED_SERVER_COMMANDS) == {
        "list",
        "add",
        "setup",
        "teardown",
        "save-key",
    }
    assert set(service.GENERATED_SERVICE_COMMANDS) == {
        "list",
        "add",
        "setup",
        "teardown",
        "logs",
    }
    assert set(model.GENERATED_MODEL_COMMANDS) == {"list"}
    assert "deploy" not in model.GENERATED_MODEL_COMMANDS
    assert not hasattr(model.model_deploy, "__workspace_command__")
