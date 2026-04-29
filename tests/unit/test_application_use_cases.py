from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from mlox.application.use_cases import models, project, servers, services


class _Session:
    def __init__(self, infra):
        self.infra = infra
        self.save_calls = 0

    def save_infrastructure(self) -> None:
        self.save_calls += 1


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_project_create_project_returns_session_payload():
    session = object()

    result = project.create_project(session, "demo")

    assert result.success is True
    assert result.data == {"session": session}


def test_servers_setup_server_calls_infra_use_case_and_saves(monkeypatch):
    server = SimpleNamespace(ip="1.2.3.4")
    bundle = SimpleNamespace(server=server)
    infra = SimpleNamespace(get_bundle_by_ip=lambda ip: bundle if ip == "1.2.3.4" else None)
    session = _Session(infra)
    called: list[object] = []
    monkeypatch.setattr(
        servers.infra_use_cases,
        "setup_server",
        lambda current_server: called.append(current_server),
    )

    result = servers.setup_server(session, ip="1.2.3.4")

    assert result.success is True
    assert called == [server]
    assert session.save_calls == 1


def test_servers_save_server_key_serializes_bundle_server(monkeypatch):
    @dataclass
    class Server:
        ip: str
        port: int

    server = Server(ip="1.2.3.4", port=22)
    bundle = SimpleNamespace(server=server)
    infra = SimpleNamespace(get_bundle_by_ip=lambda ip: bundle if ip == "1.2.3.4" else None)
    session = _Session(infra)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        servers,
        "dataclass_to_dict",
        lambda current_server: {"ip": current_server.ip, "port": current_server.port},
    )

    def fake_save_json(payload, output_path, password, overwrite):
        captured["call"] = (payload, output_path, password, overwrite)

    result = servers.save_server_key(
        session,
        fake_save_json,
        "secret",
        ip="1.2.3.4",
        output_path="/tmp/server.json",
    )

    assert result.success is True
    assert captured["call"] == (
        {"ip": "1.2.3.4", "port": 22},
        "/tmp/server.json",
        "secret",
        True,
    )


def test_services_setup_service_calls_infra_use_case_and_saves(monkeypatch):
    service = SimpleNamespace(name="svc")
    infra = SimpleNamespace(get_service=lambda name: service if name == "svc" else None)
    session = _Session(infra)
    called: list[tuple[object, object]] = []
    monkeypatch.setattr(
        services.infra_use_cases,
        "setup_service",
        lambda current_infra, current_service: called.append(
            (current_infra, current_service)
        ),
    )

    result = services.setup_service(session, name="svc")

    assert result.success is True
    assert called == [(infra, service)]
    assert session.save_calls == 1


def test_services_service_logs_uses_first_label_when_none_provided():
    service = SimpleNamespace(
        name="svc",
        compose_service_names={"api": "container-api", "worker": "container-worker"},
        compose_service_log_tail=lambda conn, label, tail: f"{label}:{tail}",
    )
    bundle = SimpleNamespace(server=SimpleNamespace(get_server_connection=lambda: _Connection()))
    infra = SimpleNamespace(
        get_service=lambda name: service if name == "svc" else None,
        get_bundle_by_service=lambda current_service: bundle if current_service is service else None,
    )
    session = _Session(infra)

    result = services.service_logs(session, name="svc", tail=25)

    assert result.success is True
    assert result.data == {"logs": "api:25"}


def test_models_list_models_fails_for_unknown_registry():
    infra = SimpleNamespace(
        filter_by_group=lambda group: []
        if group == "model-server"
        else [SimpleNamespace(name="registry-a", list_models=lambda: [])],
    )
    session = _Session(infra)

    result = models.list_models(session, registry_name="missing")

    assert result.success is False
    assert result.code == 13


def test_models_deploy_model_passes_registry_credentials_and_sets_up_service():
    registry = SimpleNamespace(
        name="registry-a",
        get_secrets=lambda: {
            "service_url": "http://registry",
            "username": "alice",
            "password": "pw",
        },
    )
    infra = SimpleNamespace(
        get_bundle_by_ip=lambda ip: object() if ip == "10.0.0.2" else None,
        filter_by_group=lambda group: [registry] if group == "model-registry" else [],
    )
    session = _Session(infra)
    service = SimpleNamespace(name="model-svc")
    captured: dict[str, object] = {}

    def fake_add_service(current_session, **kwargs):
        captured["add"] = (current_session, kwargs)
        return SimpleNamespace(success=True, data={"service": service})

    def fake_setup_service(current_session, *, name):
        captured["setup"] = (current_session, name)
        return SimpleNamespace(success=True, data={"name": name})

    result = models.deploy_model(
        session,
        fake_add_service,
        fake_setup_service,
        registry_name="registry-a",
        model_name="fraud-model",
        model_version="7",
        server_ip="10.0.0.2",
        template_id="mlserver-template",
    )

    assert result.success is True
    assert captured["add"] == (
        session,
        {
            "server_ip": "10.0.0.2",
            "template_id": "mlserver-template",
            "params": {
                "${MODEL_NAME}": "fraud-model/7",
                "${TRACKING_URI}": "http://registry",
                "${TRACKING_USER}": "alice",
                "${TRACKING_PW}": "pw",
            },
        },
    )
    assert captured["setup"] == (session, "model-svc")
