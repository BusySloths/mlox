from __future__ import annotations

from types import SimpleNamespace

from mlox.application.facade import ProjectApplication
from mlox.application.result import OperationResult
from mlox.project.aggregate import ProjectAggregate
from mlox.session import ProjectSession


class _Session:
    def __init__(self):
        self.project = ProjectAggregate(name="demo")
        self.password = "pw"
        self.commit_calls = 0
        self.reload_calls = 0

    def commit(self):
        self.commit_calls += 1

    def reload(self):
        self.reload_calls += 1
        return self.project


def test_successful_mutation_commits(monkeypatch):
    session = _Session()
    application = ProjectApplication.from_session(session)
    monkeypatch.setattr(
        "mlox.application.facade.servers.setup_server",
        lambda project, ip: OperationResult(True, 0, "ok"),
    )

    result = application.setup_server(ip="1.2.3.4")

    assert result.success
    assert session.commit_calls == 1
    assert session.reload_calls == 0


def test_failed_mutation_reloads_without_commit(monkeypatch):
    session = _Session()
    application = ProjectApplication.from_session(session)
    monkeypatch.setattr(
        "mlox.application.facade.servers.setup_server",
        lambda project, ip: OperationResult(False, 5, "missing"),
    )

    result = application.setup_server(ip="missing")

    assert not result.success
    assert session.commit_calls == 0
    assert session.reload_calls == 1


def test_exception_reloads_and_returns_failure(monkeypatch):
    session = _Session()
    application = ProjectApplication.from_session(session)

    def fail(project, ip):
        project.descr = "partial"
        raise RuntimeError("boom")

    monkeypatch.setattr("mlox.application.facade.servers.setup_server", fail)

    result = application.setup_server(ip="1.2.3.4")

    assert not result.success
    assert "boom" in result.message
    assert session.reload_calls == 1


def test_failed_mutation_discards_partial_project_changes(tmp_path, monkeypatch):
    session = ProjectSession.create(str(tmp_path / "demo"), "pw")
    application = ProjectApplication.from_session(session)

    def fail(project, ip):
        project.descr = "partial"
        return OperationResult(False, 1, "failed")

    monkeypatch.setattr("mlox.application.facade.servers.setup_server", fail)

    result = application.setup_server(ip="1.2.3.4")

    assert not result.success
    assert application.project.descr == ""


def test_read_operations_use_project(monkeypatch):
    session = _Session()
    application = ProjectApplication.from_session(session)
    captured = {}

    def list_servers(project):
        captured["project"] = project
        return OperationResult(True, 0, "ok", {"servers": []})

    monkeypatch.setattr("mlox.application.facade.servers.list_servers", list_servers)

    result = application.list_servers()

    assert result.success
    assert captured["project"] is session.project


def test_config_operations_use_catalog_loaders(monkeypatch):
    monkeypatch.setattr(
        "mlox.application.facade.load_all_server_configs",
        lambda: [SimpleNamespace(id="server", path="/server")],
    )
    monkeypatch.setattr(
        "mlox.application.facade.load_all_service_configs",
        lambda: [SimpleNamespace(id="service", path="/service")],
    )

    server_result = ProjectApplication.list_server_configs()
    service_result = ProjectApplication.list_service_configs()

    assert server_result.data["configs"][0]["id"] == "server"
    assert service_result.data["configs"][0]["id"] == "service"
