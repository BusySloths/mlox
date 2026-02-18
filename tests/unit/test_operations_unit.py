from __future__ import annotations

from types import SimpleNamespace

import pytest

from mlox.operations import (
    OperationResult,
    _SessionCache,
    _load_session,
    add_server,
    add_service,
    create_project,
    deploy_model,
    list_models,
    list_server_configs,
    list_servers,
    list_service_configs,
    list_services,
    service_logs,
)


class _Secrets:
    def __init__(self, ok=True):
        self._ok = ok

    def is_working(self):
        return self._ok


class _Infra:
    def __init__(self):
        self.bundles = []

    def add_server(self, config, params):
        return {"config": config, "params": params}

    def add_service(self, server_ip, config, params):
        svc = SimpleNamespace(name="svc-new")
        bundle = SimpleNamespace(services=[svc])
        return bundle


class _Session:
    def __init__(self, secrets=None):
        self.secrets = secrets
        self.infra = _Infra()


@pytest.fixture
def patch_session_type(monkeypatch):
    monkeypatch.setattr("mlox.operations.MloxSession", _Session)


def test_session_cache_invalidate_by_project():
    cache = _SessionCache()
    cache.set("p1", "a", object())
    cache.set("p2", "a", object())

    cache.invalidate("p1")

    assert cache.get("p1", "a") is None
    assert cache.get("p2", "a") is not None


def test_load_session_from_cache(monkeypatch):
    from mlox import operations

    cached = _Session(_Secrets(ok=True))
    operations._SESSION_CACHE.invalidate()
    operations._SESSION_CACHE.set("p", "pw", cached)

    result = _load_session("p", "pw")

    assert result.success is True
    assert result.data is cached


def test_load_session_invalidates_non_working_cached_secret(monkeypatch):
    from mlox import operations

    cached = _Session(_Secrets(ok=False))
    operations._SESSION_CACHE.invalidate()
    operations._SESSION_CACHE.set("p", "pw", cached)
    monkeypatch.setattr("mlox.operations.MloxSession", lambda project_name, password: _Session(_Secrets(ok=True)))

    result = _load_session("p", "pw")

    assert result.success is True
    assert result.message == "Session loaded."


def test_load_session_failure(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr("mlox.operations.MloxSession", _boom)

    result = _load_session("p", "pw", refresh=True)

    assert result.success is False
    assert result.code == 1


def test_create_project_success(monkeypatch, patch_session_type):
    monkeypatch.setattr("mlox.operations._load_session", lambda *args, **kwargs: OperationResult(True, 0, "ok", _Session()))

    result = create_project("p", "pw")

    assert result.success
    assert "session" in result.data


def test_list_servers_formats_payload(monkeypatch, patch_session_type):
    srv = SimpleNamespace(ip="1.2.3.4", state="running", backend=["docker"], discovered=True, service_config_id="tmpl", port=22)
    bundle = SimpleNamespace(server=srv, services=[1, 2])
    session = _Session()
    session.infra.bundles = [bundle]
    monkeypatch.setattr("mlox.operations._load_session", lambda *args, **kwargs: OperationResult(True, 0, "ok", session))

    result = list_servers("p", "pw")

    assert result.success
    assert result.data["servers"][0]["service_count"] == 2


def test_add_server_template_not_found(monkeypatch, patch_session_type):
    monkeypatch.setattr("mlox.operations._load_session", lambda *args, **kwargs: OperationResult(True, 0, "ok", _Session()))
    monkeypatch.setattr("mlox.operations._load_config_from_path", lambda p: None)

    result = add_server("p", "pw", template_path="a/b", ip="1.1.1.1", port=22, root_user="u", root_password="pw")

    assert result.code == 3


def test_add_service_and_list_services(monkeypatch, patch_session_type):
    session = _Session()

    svc = SimpleNamespace(
        name="svc1",
        service_config_id="cfg",
        state="running",
        compose_service_names={"api": "container"},
        service_ports={"http": 8080},
        service_urls={"ui": "http://localhost"},
    )
    session.infra.bundles = [SimpleNamespace(server=SimpleNamespace(ip="1.1.1.1"), services=[svc])]
    session.save_infrastructure = lambda: None

    monkeypatch.setattr("mlox.operations._load_session", lambda *args, **kwargs: OperationResult(True, 0, "ok", session))
    monkeypatch.setattr("mlox.operations.load_service_config_by_id", lambda _id: {"id": _id})

    add_result = add_service("p", "pw", server_ip="1.1.1.1", template_id="svc-template")
    list_result = list_services("p", "pw")

    assert add_result.success
    assert list_result.data["services"][0]["ports"] == ["http:8080"]


def test_service_logs_without_labels(monkeypatch, patch_session_type):
    svc = SimpleNamespace(name="svc", compose_service_names={})
    infra = SimpleNamespace(get_service=lambda name: svc)
    session = _Session()
    session.infra = infra
    monkeypatch.setattr("mlox.operations._load_session", lambda *args, **kwargs: OperationResult(True, 0, "ok", session))

    result = service_logs("p", "pw", name="svc")

    assert result.code == 9


def test_list_models_and_deploy_model(monkeypatch, patch_session_type):
    class Registry:
        name = "reg"

        def list_models(self):
            return [{"Model": "m", "Version": "1"}]

        def get_secrets(self):
            return {"service_url": "uri", "username": "u", "password": "p"}

    class Server:
        name = "srv"

        def is_model(self, model):
            return model == "reg:m:1"

    infra = SimpleNamespace(
        filter_by_group=lambda g: [Server()] if g == "model-server" else [Registry()],
        get_bundle_by_ip=lambda ip: object(),
    )
    session = _Session()
    session.infra = infra
    monkeypatch.setattr("mlox.operations._load_session", lambda *args, **kwargs: OperationResult(True, 0, "ok", session))
    monkeypatch.setattr("mlox.operations.ModelRegistry", object)
    monkeypatch.setattr("mlox.operations.ModelServer", object)

    models = list_models("p", "pw")

    assert models.success
    assert models.data["models"][0]["is_deployed"] is True

    svc = SimpleNamespace(name="ms")
    monkeypatch.setattr("mlox.operations.add_service", lambda **kwargs: OperationResult(True, 0, "ok", {"service": svc}))
    monkeypatch.setattr("mlox.operations.setup_service", lambda project, password, name: OperationResult(True, 0, "ok", {"name": name}))
    monkeypatch.setattr("mlox.operations.ModelServer", object)

    deployed = deploy_model("p", "pw", registry_name="reg", model_name="m", model_version="1", server_ip="10.0.0.1")
    assert deployed.success


def test_list_config_operations(monkeypatch):
    monkeypatch.setattr("mlox.operations.load_all_server_configs", lambda: [SimpleNamespace(id="s1", path="/s1")])
    monkeypatch.setattr("mlox.operations.load_all_service_configs", lambda: [SimpleNamespace(id="v1", path="/v1")])

    servers = list_server_configs()
    services = list_service_configs()

    assert servers.success and services.success
    assert servers.data["configs"][0]["id"] == "s1"
