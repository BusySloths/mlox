from __future__ import annotations

from types import SimpleNamespace

from mlox.application import facade
from mlox.application.result import OperationResult


def test_create_project_creates_session_and_delegates(monkeypatch):
    session = SimpleNamespace(project=SimpleNamespace(name="demo"))
    calls: dict[str, object] = {}

    monkeypatch.setattr(facade.MloxSession, "create", lambda name, password: session)
    monkeypatch.setattr(
        facade._SESSION_CACHE,
        "set",
        lambda name, password, value: calls.update(cache=(name, password, value)),
    )

    def fake_create_project(current_session, name):
        calls["create"] = (current_session, name)
        return OperationResult(True, 0, "created", {"session": current_session})

    monkeypatch.setattr(facade.project, "create_project", fake_create_project)
    result = facade.create_project("demo", "pw")

    assert result.success is True
    assert calls["create"] == (session, "demo")
    assert calls["cache"] == ("demo", "pw", session)


def test_list_server_configs_uses_catalog_loader(monkeypatch):
    captured: dict[str, object] = {}

    def fake_list_server_configs(loader):
        captured["loader"] = loader
        return OperationResult(True, 0, "ok", {"configs": []})

    monkeypatch.setattr(facade.servers, "list_server_configs", fake_list_server_configs)

    result = facade.list_server_configs()

    assert result.success is True
    assert captured["loader"] is facade.load_all_server_configs


def test_invalidate_session_cache_clears_project_entries():
    cache = facade._SESSION_CACHE
    cache.invalidate()
    cache.set("project-a", "pw", object())
    cache.set("project-b", "pw", object())

    facade.invalidate_session_cache("project-a")

    assert cache.get("project-a", "pw") is None
    assert cache.get("project-b", "pw") is not None
    cache.invalidate()
