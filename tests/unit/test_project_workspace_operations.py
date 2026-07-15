from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from mlox.application.result import OperationResult
from mlox.project import ProjectWorkspace
from mlox.project.state import WorkspaceState


class _Repository:
    def __init__(self):
        self.password = "pw"
        self.path = SimpleNamespace()


def _workspace() -> ProjectWorkspace:
    return ProjectWorkspace(_Repository(), WorkspaceState(name="demo"))


def test_successful_mutation_commits(monkeypatch):
    workspace = _workspace()
    workspace.commit = mock.Mock()
    workspace.reload = mock.Mock()
    monkeypatch.setattr(
        "mlox.project.workspace.servers.setup_server",
        lambda project, ip: OperationResult(True, 0, "ok"),
    )

    result = workspace.setup_server(ip="1.2.3.4")

    assert result.success
    workspace.commit.assert_called_once_with()
    workspace.reload.assert_not_called()


def test_server_health_mutation_commits(monkeypatch):
    workspace = _workspace()
    server = SimpleNamespace(ip="1.2.3.4")
    workspace.infrastructure.bundles.append(SimpleNamespace(server=server, services=[]))
    workspace.commit = mock.Mock()
    workspace.reload = mock.Mock()
    monkeypatch.setattr(
        "mlox.project.workspace.servers.check_server_health",
        lambda server_arg: OperationResult(True, 0, "checked", {"server": server_arg}),
    )

    result = workspace.check_server_health(ip="1.2.3.4")

    assert result.success
    workspace.commit.assert_called_once_with()
    workspace.reload.assert_not_called()


def test_service_health_mutation_commits(monkeypatch):
    workspace = _workspace()
    workspace.commit = mock.Mock()
    workspace.reload = mock.Mock()
    monkeypatch.setattr(
        "mlox.project.workspace.services.check_service_health",
        lambda project, name: OperationResult(True, 0, "checked", {"name": name}),
    )

    result = workspace.check_service_health(name="svc")

    assert result.success
    workspace.commit.assert_called_once_with()
    workspace.reload.assert_not_called()


def test_failed_mutation_reloads_without_commit(monkeypatch):
    workspace = _workspace()
    workspace.commit = mock.Mock()
    workspace.reload = mock.Mock()
    monkeypatch.setattr(
        "mlox.project.workspace.servers.setup_server",
        lambda project, ip: OperationResult(False, 5, "missing"),
    )

    result = workspace.setup_server(ip="missing")

    assert not result.success
    workspace.commit.assert_not_called()
    workspace.reload.assert_called_once_with()


def test_exception_reloads_and_returns_failure(monkeypatch):
    workspace = _workspace()
    workspace.reload = mock.Mock()

    def fail(project, ip):
        project.descr = "partial"
        raise RuntimeError("boom")

    monkeypatch.setattr("mlox.project.workspace.servers.setup_server", fail)

    result = workspace.setup_server(ip="1.2.3.4")

    assert not result.success
    assert "boom" in result.message
    workspace.reload.assert_called_once_with()


def test_failed_mutation_discards_partial_project_changes(tmp_path, monkeypatch):
    workspace = ProjectWorkspace.create(str(tmp_path / "demo"), "pw")

    def fail(project, ip):
        project.descr = "partial"
        return OperationResult(False, 1, "failed")

    monkeypatch.setattr("mlox.project.workspace.servers.setup_server", fail)

    result = workspace.setup_server(ip="1.2.3.4")

    assert not result.success
    assert workspace.descr == ""


def test_read_operations_use_project(monkeypatch):
    workspace = _workspace()
    captured = {}

    def list_servers(project):
        captured["project"] = project
        return OperationResult(True, 0, "ok", {"servers": []})

    monkeypatch.setattr("mlox.project.workspace.servers.list_servers", list_servers)

    result = workspace.list_servers()

    assert result.success
    assert captured["project"].infrastructure is workspace.infrastructure


def test_config_operations_use_catalog_loaders(monkeypatch):
    monkeypatch.setattr(
        "mlox.project.workspace.load_all_server_configs",
        lambda: [SimpleNamespace(id="server", path="/server")],
    )
    monkeypatch.setattr(
        "mlox.project.workspace.load_all_service_configs",
        lambda: [SimpleNamespace(id="service", path="/service")],
    )

    server_result = ProjectWorkspace.list_server_configs()
    service_result = ProjectWorkspace.list_service_configs()

    assert server_result.data["configs"][0]["id"] == "server"
    assert service_result.data["configs"][0]["id"] == "service"
