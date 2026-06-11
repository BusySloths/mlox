from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from mlox.application.use_cases import models, project, servers, services


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _project(infrastructure):
    return SimpleNamespace(name="demo", infrastructure=infrastructure)


def test_project_create_project_returns_project_payload():
    current = SimpleNamespace(name="demo")

    result = project.create_project(current)

    assert result.success
    assert result.data == {"project": current}


def test_servers_setup_server_invokes_server_without_persisting():
    calls = []
    server = SimpleNamespace(setup=lambda: calls.append("setup"))
    bundle = SimpleNamespace(server=server)
    current = _project(
        SimpleNamespace(get_bundle_by_ip=lambda ip: bundle if ip == "1.2.3.4" else None)
    )

    result = servers.setup_server(current, ip="1.2.3.4")

    assert result.success
    assert calls == ["setup"]


def test_servers_save_server_key_serializes_bundle_server(monkeypatch):
    @dataclass
    class Server:
        ip: str
        port: int

    server = Server(ip="1.2.3.4", port=22)
    current = _project(
        SimpleNamespace(
            get_bundle_by_ip=lambda ip: SimpleNamespace(server=server)
            if ip == server.ip
            else None
        )
    )
    captured = {}
    monkeypatch.setattr(
        servers,
        "dataclass_to_dict",
        lambda value: {"ip": value.ip, "port": value.port},
    )

    result = servers.save_server_key(
        current,
        lambda *args: captured.update(call=args),
        "secret",
        ip=server.ip,
        output_path="/tmp/server.json",
    )

    assert result.success
    assert captured["call"] == (
        {"ip": "1.2.3.4", "port": 22},
        "/tmp/server.json",
        "secret",
        True,
    )


def test_services_setup_service_runs_runtime_steps():
    calls = []
    service = SimpleNamespace(
        name="svc",
        setup=lambda conn: calls.append("setup"),
        spin_up=lambda conn: calls.append("spin_up"),
    )
    bundle = SimpleNamespace(
        server=SimpleNamespace(get_server_connection=lambda: _Connection())
    )
    current = _project(
        SimpleNamespace(
            get_service=lambda name: service if name == "svc" else None,
            get_bundle_by_service=lambda value: bundle if value is service else None,
        )
    )

    result = services.setup_service(current, name="svc")

    assert result.success
    assert calls == ["setup", "spin_up"]


def test_models_list_models_fails_for_unknown_registry():
    current = _project(
        SimpleNamespace(
            filter_by_group=lambda group: []
            if group == "model-server"
            else [SimpleNamespace(name="registry-a", list_models=lambda: [])]
        )
    )

    result = models.list_models(current, registry_name="missing")

    assert not result.success
    assert result.code == 13
