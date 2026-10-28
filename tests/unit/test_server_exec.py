import json
from types import SimpleNamespace
from unittest.mock import Mock

from invoke.exceptions import CommandTimedOut
from typer.testing import CliRunner

from mlox import cli
from mlox.application.result import OperationResult
from mlox.application.use_cases.servers import execute_server_command
from mlox.project import ProjectWorkspace
from mlox.server import ServerCapability


class Connection:
    def __init__(self, result):
        self.run = Mock(return_value=result)
        self.sudo = Mock(return_value=result)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


def project_for(connection, capabilities=None):
    server = SimpleNamespace(
        capabilities={ServerCapability.TERMINAL} if capabilities is None else capabilities,
        get_server_connection=lambda: connection,
    )
    bundle = SimpleNamespace(server=server)
    return SimpleNamespace(infrastructure=SimpleNamespace(get_bundle_by_ip=lambda ip: bundle if ip == "host" else None))


def test_workspace_exec_captures_output_and_uses_managed_connection():
    connection = Connection(SimpleNamespace(stdout="hello\n", stderr="warning\n", exited=0))
    workspace = ProjectWorkspace.__new__(ProjectWorkspace)
    workspace._state = project_for(connection)
    result = workspace.execute_server_command(ip="host", command="echo hello", sudo=True, timeout=12)
    assert result.success
    assert result.data == {"stdout": "hello\n", "stderr": "warning\n", "exit_code": 0, "timed_out": False}
    connection.sudo.assert_called_once_with("echo hello", hide=True, warn=True, pty=False, in_stream=False, timeout=12)
    connection.run.assert_not_called()
    assert connection.closed


def test_remote_failure_and_timeout_preserve_partial_output():
    connection = Connection(SimpleNamespace(stdout="partial", stderr="bad", exited=7))
    result = execute_server_command(project_for(connection), ip="host", command="false")
    assert not result.success and result.code == 7
    assert result.data["stderr"] == "bad" and result.data["exit_code"] == 7
    connection.run.side_effect = CommandTimedOut(SimpleNamespace(stdout="partial", stderr="late"), timeout=1)
    result = execute_server_command(project_for(connection), ip="host", command="sleep 2", timeout=1)
    assert result.code == 124 and result.data["timed_out"]
    assert result.data["stdout"] == "partial" and result.data["exit_code"] is None


def test_exec_rejects_unknown_or_non_ssh_server():
    connection = Connection(None)
    assert not execute_server_command(project_for(connection), ip="missing", command="true").success
    assert not execute_server_command(project_for(connection, set()), ip="host", command="true").success
    connection.run.assert_not_called()


def test_generated_cli_exec_json_and_failure_output(monkeypatch):
    result = OperationResult(False, 3, "Command exited with status 3.", {
        "stdout": "output\n", "stderr": "error\n", "exit_code": 3, "timed_out": False,
    })
    operation = Mock(return_value=result)
    monkeypatch.setattr(ProjectWorkspace, "open", Mock(return_value=SimpleNamespace(execute_server_command=operation)))
    args = ["server", "exec", "--project", "project", "--password", "pw", "--ip", "host", "--command", "false", "--sudo", "--timeout", "12"]
    runner = CliRunner()
    response = runner.invoke(cli.app, ["--output", "json", *args])
    assert response.exit_code == 3
    assert json.loads(response.stdout)["data"] == result.data
    operation.assert_called_with(ip="host", command="false", sudo=True, timeout=12)
    response = runner.invoke(cli.app, args)
    assert response.exit_code == 3 and response.stdout == "output\n"
    assert "error\n" in response.stderr


def test_sudo_prompt_is_not_returned():
    connection = Connection(SimpleNamespace(stdout="ok", stderr="[sudo] password: warning", exited=0))
    result = execute_server_command(project_for(connection), ip="host", command="true", sudo=True)
    assert result.data["stderr"] == "warning"
