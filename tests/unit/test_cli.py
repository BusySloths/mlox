import types
from unittest import mock

import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner

from mlox import cli


runner = CliRunner()


class DummySecrets:
    def __init__(self, working: bool) -> None:
        self._working = working

    def is_working(self) -> bool:
        return self._working


class DummySession:
    def __init__(self, *, working_secrets: bool = True):
        self.secrets = DummySecrets(working_secrets)


def test_parse_kv_parses_pairs():
    data = ["FOO=bar", "BAZ=qux", "invalid", "COMPLEX=value=with=equals"]
    result = cli.parse_kv(data)

    assert result == {
        "FOO": "bar",
        "BAZ": "qux",
        "COMPLEX": "value=with=equals",
    }


def test_get_session_success(monkeypatch):
    dummy_session = DummySession()
    monkeypatch.setattr(cli, "MloxSession", mock.Mock(return_value=dummy_session))

    session = cli.get_session("project", "password")

    assert session is dummy_session


def test_get_session_secrets_failure(monkeypatch, capsys):
    mock_session = mock.Mock()
    mock_session.secrets.is_working.return_value = False
    monkeypatch.setattr(cli, "MloxSession", mock.Mock(return_value=mock_session))

    with pytest.raises(typer.Exit) as exc_info:
        cli.get_session("project", "password")

    assert exc_info.value.exit_code == 2
    captured = capsys.readouterr()
    assert "Could not initialize session" in captured.err


def test_get_session_exception(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "MloxSession",
        mock.Mock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(typer.Exit) as exc_info:
        cli.get_session("project", "password")

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Failed to load session" in captured.err


def test_server_list_no_servers(monkeypatch):
    session = types.SimpleNamespace(infra=types.SimpleNamespace(bundles=[]))
    monkeypatch.setattr(cli, "get_session", mock.Mock(return_value=session))

    result = runner.invoke(
        cli.app,
        ["server", "list", "proj", "--password", "pw"],
    )

    assert result.exit_code == 0
    assert "No servers found." in result.stdout


def test_server_list_outputs_servers(monkeypatch):
    bundle = types.SimpleNamespace(
        server=types.SimpleNamespace(ip="1.1.1.1", state="running"),
        services=[1, 2, 3],
    )
    session = types.SimpleNamespace(infra=types.SimpleNamespace(bundles=[bundle]))
    monkeypatch.setattr(cli, "get_session", mock.Mock(return_value=session))

    result = runner.invoke(
        cli.app,
        ["server", "list", "proj", "--password", "pw"],
    )

    assert result.exit_code == 0
    assert "1.1.1.1 (running) - 3 services" in result.stdout


def test_server_add_template_missing(monkeypatch):
    session = types.SimpleNamespace(
        infra=types.SimpleNamespace(add_server=mock.Mock()),
        save_infrastructure=mock.Mock(),
    )
    monkeypatch.setattr(cli, "get_session", mock.Mock(return_value=session))
    monkeypatch.setattr(cli, "_load_config_from_path", mock.Mock(return_value=None))

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
    assert "Server template not found" in result.stderr
    session.infra.add_server.assert_not_called()


def test_server_add_success(monkeypatch):
    infra = mock.Mock()
    bundle = types.SimpleNamespace(
        server=types.SimpleNamespace(ip="1.2.3.4", state="new"),
        services=["svc"],
    )
    infra.add_server.return_value = bundle
    session = types.SimpleNamespace(
        infra=infra,
        save_infrastructure=mock.Mock(),
    )
    monkeypatch.setattr(cli, "get_session", mock.Mock(return_value=session))
    monkeypatch.setattr(cli, "_load_config_from_path", mock.Mock(return_value={}))

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
    assert "Added server 1.2.3.4" in result.stdout
    infra.add_server.assert_called_once()
    session.save_infrastructure.assert_called_once()
    _, kwargs = infra.add_server.call_args
    assert kwargs["params"]["${MLOX_ROOT_PW}"] == "secret"
    assert kwargs["params"]["CUSTOM"] == "value"


def test_service_list_no_services(monkeypatch):
    bundle = types.SimpleNamespace(
        services=[], server=types.SimpleNamespace(ip="1.1.1.1")
    )
    session = types.SimpleNamespace(infra=types.SimpleNamespace(bundles=[bundle]))
    monkeypatch.setattr(cli, "get_session", mock.Mock(return_value=session))

    result = runner.invoke(
        cli.app,
        ["service", "list", "proj", "--password", "pw"],
    )

    assert result.exit_code == 0
    assert "No services found." in result.stdout


def test_service_list_outputs(monkeypatch):
    service = types.SimpleNamespace(name="svc", service_config_id="svc-template")
    bundle = types.SimpleNamespace(
        services=[service],
        server=types.SimpleNamespace(ip="1.1.1.1"),
    )
    session = types.SimpleNamespace(infra=types.SimpleNamespace(bundles=[bundle]))
    monkeypatch.setattr(cli, "get_session", mock.Mock(return_value=session))

    result = runner.invoke(
        cli.app,
        ["service", "list", "proj", "--password", "pw"],
    )

    assert result.exit_code == 0
    assert "svc (svc-template) on 1.1.1.1" in result.stdout


def test_server_configs_list_no_configs(monkeypatch):
    monkeypatch.setattr(cli, "load_all_server_configs", mock.Mock(return_value=[]))

    result = runner.invoke(cli.app, ["server", "configs", "list"])

    assert result.exit_code == 0
    assert "No server configs found." in result.stdout


def test_server_configs_list_outputs(monkeypatch):
    configs = [types.SimpleNamespace(id="srv", path="servers/srv.yaml")]
    monkeypatch.setattr(cli, "load_all_server_configs", mock.Mock(return_value=configs))

    result = runner.invoke(cli.app, ["server", "configs", "list"])

    assert result.exit_code == 0
    assert "srv - servers/srv.yaml" in result.stdout


def test_service_configs_list_no_configs(monkeypatch):
    monkeypatch.setattr(cli, "load_all_service_configs", mock.Mock(return_value=[]))

    result = runner.invoke(cli.app, ["service", "configs", "list"])

    assert result.exit_code == 0
    assert "No service configs found." in result.stdout


def test_service_configs_list_outputs(monkeypatch):
    configs = [types.SimpleNamespace(id="svc", path="services/svc.yaml")]
    monkeypatch.setattr(
        cli, "load_all_service_configs", mock.Mock(return_value=configs)
    )

    result = runner.invoke(cli.app, ["service", "configs", "list"])

    assert result.exit_code == 0
    assert "svc - services/svc.yaml" in result.stdout
