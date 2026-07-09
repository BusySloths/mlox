import pytest
from types import SimpleNamespace
from unittest import mock

from typer.testing import CliRunner

from mlox import cli
from mlox.project import ProjectWorkspace
from mlox.application.result import OperationResult

typer = pytest.importorskip("typer")
runner = CliRunner()


def _patch_application(monkeypatch, method_name, result):
    method = mock.Mock(return_value=result)
    application = SimpleNamespace(**{method_name: method})
    monkeypatch.setattr(ProjectWorkspace, "open", mock.Mock(return_value=application))
    return method


def test_parse_kv_parses_pairs():
    data = ["FOO=bar", "BAZ=qux", "invalid", "COMPLEX=value=with=equals"]
    result = cli.parse_kv(data)

    assert result == {
        "FOO": "bar",
        "BAZ": "qux",
        "COMPLEX": "value=with=equals",
    }


def test_handle_result_success():
    result = OperationResult(True, 0, "ok")

    assert cli._handle_result(result) is result


def test_handle_result_failure(capsys):
    result = OperationResult(False, 3, "boom")

    with pytest.raises(typer.Exit) as exc_info:
        cli._handle_result(result)

    assert exc_info.value.exit_code == 3
    captured = capsys.readouterr()
    assert "boom" in captured.err


def test_server_list_no_servers(monkeypatch):
    operation_result = OperationResult(True, 0, "No servers found.", {"servers": []})
    _patch_application(monkeypatch, "list_servers", operation_result)

    result = runner.invoke(cli.app, ["server", "list", "proj", "--password", "pw"])

    assert result.exit_code == 0
    assert "No servers found." in result.stdout


def test_server_list_outputs_servers(monkeypatch):
    payload = {"servers": [{"ip": "1.1.1.1", "state": "running", "service_count": 3}]}
    operation_result = OperationResult(
        True, 0, "Servers retrieved successfully.", payload
    )
    mock_list = mock.Mock(return_value=operation_result)
    application = SimpleNamespace(list_servers=mock_list)
    monkeypatch.setattr(ProjectWorkspace, "open", mock.Mock(return_value=application))

    result = runner.invoke(cli.app, ["server", "list", "proj", "--password", "pw"])

    assert result.exit_code == 0
    assert "Servers" in result.stdout
    assert "| IP" in result.stdout
    assert "| 1.1.1.1" in result.stdout
    assert "running" in result.stdout
    mock_list.assert_called_once_with()


def test_server_add_failure(monkeypatch):
    operation_result = OperationResult(False, 1, "Server template not found.")
    mock_add = mock.Mock(return_value=operation_result)
    application = SimpleNamespace(add_server=mock_add)
    monkeypatch.setattr(ProjectWorkspace, "open", mock.Mock(return_value=application))

    result = runner.invoke(
        cli.app,
        [
            "server",
            "add",
            "proj",
            "--password",
            "pw",
            "--server-template",
            "template",
            "--ip",
            "1.2.3.4",
            "--root-pw",
            "secret",
        ],
    )

    assert result.exit_code == 1
    assert "Server template not found." in result.stderr
    mock_add.assert_called_once()


def test_server_add_success(monkeypatch):
    operation_result = OperationResult(True, 0, "Added server 1.2.3.4.")
    mock_add = mock.Mock(return_value=operation_result)
    application = SimpleNamespace(add_server=mock_add)
    monkeypatch.setattr(ProjectWorkspace, "open", mock.Mock(return_value=application))

    result = runner.invoke(
        cli.app,
        [
            "server",
            "add",
            "proj",
            "--password",
            "pw",
            "--server-template",
            "template",
            "--ip",
            "1.2.3.4",
            "--root-pw",
            "secret",
            "--param",
            "CUSTOM=value",
        ],
    )

    assert result.exit_code == 0
    assert "Added server 1.2.3.4." in result.stdout
    mock_add.assert_called_once()
    _, kwargs = mock_add.call_args
    assert kwargs["extra_params"]["CUSTOM"] == "value"


def test_service_list_no_services(monkeypatch):
    operation_result = OperationResult(True, 0, "No services found.", {"services": []})
    _patch_application(monkeypatch, "list_services", operation_result)

    result = runner.invoke(cli.app, ["service", "list", "proj", "--password", "pw"])

    assert result.exit_code == 0
    assert "No services found." in result.stdout


def test_service_list_outputs(monkeypatch):
    payload = {
        "services": [
            {
                "name": "svc",
                "service_config_id": "svc-template",
                "server_ip": "1.1.1.1",
            }
        ]
    }
    operation_result = OperationResult(
        True, 0, "Services retrieved successfully.", payload
    )
    _patch_application(monkeypatch, "list_services", operation_result)

    result = runner.invoke(cli.app, ["service", "list", "proj", "--password", "pw"])

    assert result.exit_code == 0
    assert "Services" in result.stdout
    assert "| Service" in result.stdout
    assert "| svc" in result.stdout
    assert "svc-template" in result.stdout
    assert "1.1.1.1" in result.stdout


def test_server_configs_list_no_configs(monkeypatch):
    operation_result = OperationResult(
        True, 0, "No server configs found.", {"configs": []}
    )
    monkeypatch.setattr(
        ProjectWorkspace,
        "list_server_configs",
        mock.Mock(return_value=operation_result),
    )

    result = runner.invoke(cli.app, ["server", "configs", "list"])

    assert result.exit_code == 0
    assert "No server configs found." in result.stdout


def test_server_configs_list_outputs(monkeypatch):
    payload = {"configs": [{"id": "srv", "path": "servers/srv.yaml"}]}
    operation_result = OperationResult(True, 0, "Server configs retrieved.", payload)
    monkeypatch.setattr(
        ProjectWorkspace,
        "list_server_configs",
        mock.Mock(return_value=operation_result),
    )

    result = runner.invoke(cli.app, ["server", "configs", "list"])

    assert result.exit_code == 0
    assert "Server Configs" in result.stdout
    assert "| ID" in result.stdout
    assert "| srv" in result.stdout
    assert "servers/srv.yaml" in result.stdout


def test_service_configs_list_no_configs(monkeypatch):
    operation_result = OperationResult(
        True, 0, "No service configs found.", {"configs": []}
    )
    monkeypatch.setattr(
        ProjectWorkspace,
        "list_service_configs",
        mock.Mock(return_value=operation_result),
    )

    result = runner.invoke(cli.app, ["service", "configs", "list"])

    assert result.exit_code == 0
    assert "No service configs found." in result.stdout


def test_service_configs_list_outputs(monkeypatch):
    payload = {"configs": [{"id": "svc", "path": "services/svc.yaml"}]}
    operation_result = OperationResult(True, 0, "Service configs retrieved.", payload)
    monkeypatch.setattr(
        ProjectWorkspace,
        "list_service_configs",
        mock.Mock(return_value=operation_result),
    )

    result = runner.invoke(cli.app, ["service", "configs", "list"])

    assert result.exit_code == 0
    assert "Service Configs" in result.stdout
    assert "| ID" in result.stdout
    assert "| svc" in result.stdout
    assert "services/svc.yaml" in result.stdout


def test_start_ui_invokes_streamlit(monkeypatch):
    mock_run = mock.Mock(return_value=mock.Mock(returncode=0))
    monkeypatch.setattr(cli.subprocess, "run", mock_run)

    result = runner.invoke(cli.app, ["ui"])

    assert result.exit_code == 0
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    command = call_args.args[0]
    assert command[0] == cli.sys.executable
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4].endswith("mlox/app.py")
    assert call_args.kwargs["check"] is False


def test_start_tui_invokes_app_with_tui_environment(monkeypatch):
    mock_run = mock.Mock(return_value=mock.Mock(returncode=0))
    monkeypatch.setattr(cli.subprocess, "run", mock_run)

    result = runner.invoke(cli.app, ["tui"])

    assert result.exit_code == 0
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    command = call_args.args[0]
    assert command[0] == cli.sys.executable
    assert command[1].endswith("mlox/tui/app.py")
    assert call_args.kwargs["check"] is False
    assert call_args.kwargs["env"]["MLOX_TUI"] == "true"


def test_start_tui_exits_with_textual_return_code(monkeypatch):
    mock_run = mock.Mock(return_value=mock.Mock(returncode=7))
    monkeypatch.setattr(cli.subprocess, "run", mock_run)

    result = runner.invoke(cli.app, ["tui"])

    assert result.exit_code == 7


def test_project_new_prints_canonical_project_path_without_password(monkeypatch, tmp_path):
    application = SimpleNamespace(
        project_created=mock.Mock(
            return_value=OperationResult(True, 0, "created")
        )
    )
    monkeypatch.setattr(
        ProjectWorkspace,
        "create",
        mock.Mock(return_value=application),
    )
    result = runner.invoke(
        cli.app,
        ["project", "new", str(tmp_path / "demo"), "--password", "super-secret"],
    )
    assert result.exit_code == 0
    assert str((tmp_path / "demo.mlox").resolve()) in result.stdout
    assert "super-secret" not in result.stdout
    assert "MLOX_PROJECT_PATH" in result.stdout
