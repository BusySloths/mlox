import pytest
from unittest import mock

from typer.testing import CliRunner

from mlox import cli
from mlox.operations import OperationResult

typer = pytest.importorskip("typer")
runner = CliRunner()


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
    monkeypatch.setattr(cli.ops, "list_servers", mock.Mock(return_value=operation_result))

    result = runner.invoke(cli.app, ["server", "list", "proj", "--password", "pw"])

    assert result.exit_code == 0
    assert "No servers found." in result.stdout


def test_server_list_outputs_servers(monkeypatch):
    payload = {"servers": [{"ip": "1.1.1.1", "state": "running", "service_count": 3}]}
    operation_result = OperationResult(True, 0, "Servers retrieved successfully.", payload)
    mock_list = mock.Mock(return_value=operation_result)
    monkeypatch.setattr(cli.ops, "list_servers", mock_list)

    result = runner.invoke(cli.app, ["server", "list", "proj", "--password", "pw"])

    assert result.exit_code == 0
    assert "Servers" in result.stdout
    assert "| IP" in result.stdout
    assert "| 1.1.1.1" in result.stdout
    assert "running" in result.stdout
    mock_list.assert_called_once_with(project="proj", password="pw")


def test_server_add_failure(monkeypatch):
    operation_result = OperationResult(False, 1, "Server template not found.")
    mock_add = mock.Mock(return_value=operation_result)
    monkeypatch.setattr(cli.ops, "add_server", mock_add)

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
    monkeypatch.setattr(cli.ops, "add_server", mock_add)

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
    monkeypatch.setattr(cli.ops, "list_services", mock.Mock(return_value=operation_result))

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
    operation_result = OperationResult(True, 0, "Services retrieved successfully.", payload)
    monkeypatch.setattr(cli.ops, "list_services", mock.Mock(return_value=operation_result))

    result = runner.invoke(cli.app, ["service", "list", "proj", "--password", "pw"])

    assert result.exit_code == 0
    assert "Services" in result.stdout
    assert "| Service" in result.stdout
    assert "| svc" in result.stdout
    assert "svc-template" in result.stdout
    assert "1.1.1.1" in result.stdout


def test_server_configs_list_no_configs(monkeypatch):
    operation_result = OperationResult(True, 0, "No server configs found.", {"configs": []})
    monkeypatch.setattr(cli.ops, "list_server_configs", mock.Mock(return_value=operation_result))

    result = runner.invoke(cli.app, ["server", "configs", "list"])

    assert result.exit_code == 0
    assert "No server configs found." in result.stdout


def test_server_configs_list_outputs(monkeypatch):
    payload = {"configs": [{"id": "srv", "path": "servers/srv.yaml"}]}
    operation_result = OperationResult(True, 0, "Server configs retrieved.", payload)
    monkeypatch.setattr(cli.ops, "list_server_configs", mock.Mock(return_value=operation_result))

    result = runner.invoke(cli.app, ["server", "configs", "list"])

    assert result.exit_code == 0
    assert "Server Configs" in result.stdout
    assert "| ID" in result.stdout
    assert "| srv" in result.stdout
    assert "servers/srv.yaml" in result.stdout


def test_service_configs_list_no_configs(monkeypatch):
    operation_result = OperationResult(True, 0, "No service configs found.", {"configs": []})
    monkeypatch.setattr(cli.ops, "list_service_configs", mock.Mock(return_value=operation_result))

    result = runner.invoke(cli.app, ["service", "configs", "list"])

    assert result.exit_code == 0
    assert "No service configs found." in result.stdout


def test_service_configs_list_outputs(monkeypatch):
    payload = {"configs": [{"id": "svc", "path": "services/svc.yaml"}]}
    operation_result = OperationResult(True, 0, "Service configs retrieved.", payload)
    monkeypatch.setattr(cli.ops, "list_service_configs", mock.Mock(return_value=operation_result))

    result = runner.invoke(cli.app, ["service", "configs", "list"])

    assert result.exit_code == 0
    assert "Service Configs" in result.stdout
    assert "| ID" in result.stdout
    assert "| svc" in result.stdout
    assert "services/svc.yaml" in result.stdout
