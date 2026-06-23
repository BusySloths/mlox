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


def test_project_open_workspace_uses_project_workspace():
    workspace = SimpleNamespace(name="demo", path="demo.mlox")
    calls = []

    class Workspace:
        @staticmethod
        def open(path, password):
            calls.append(("open", path, password))
            return workspace

    result = project.open_project_workspace("demo.mlox", "pw", workspace_cls=Workspace)

    assert result.success
    assert result.data == {"workspace": workspace}
    assert calls == [("open", "demo.mlox", "pw")]


def test_project_reload_workspace_reports_failures():
    workspace = SimpleNamespace(
        path="demo.mlox",
        reload=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    result = project.reload_project_workspace(workspace)

    assert not result.success
    assert result.message == "Failed to reload infrastructure: offline"


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


def test_servers_browse_server_templates_returns_config_objects():
    configs = [SimpleNamespace(id="server-template")]

    result = servers.browse_server_templates(list_configs=lambda: configs)

    assert result.success
    assert result.data == {"configs": configs}


def test_servers_open_server_terminal_uses_launcher():
    launched = []
    server = SimpleNamespace(ip="1.2.3.4")

    result = servers.open_server_terminal(server, launcher=launched.append)

    assert result.success
    assert launched == [server]
    assert result.message == "Opened SSH terminal for 1.2.3.4."


def test_servers_get_runtime_info_collects_server_and_backend_info():
    server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"cpu_count": 4, "host": "demo"},
        get_backend_status=lambda: {"backend.is_running": True},
    )

    result = servers.get_server_runtime_info(server)

    assert result.success
    assert result.data == {
        "server_info": {"cpu_count": 4, "host": "demo"},
        "backend_info": {"backend.is_running": True},
    }


def test_servers_get_runtime_info_prefers_get_backend_info():
    server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"host": "demo"},
        get_backend_info=lambda: {"backend.kind": "custom"},
        get_backend_status=lambda: {"backend.kind": "fallback"},
    )

    result = servers.get_server_runtime_info(server)

    assert result.success
    assert result.data["backend_info"] == {"backend.kind": "custom"}


def test_servers_get_server_info_only_collects_server_info():
    server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"host": "demo"},
        get_backend_status=lambda: {"backend.is_running": True},
    )

    result = servers.get_server_info(server)

    assert result.success
    assert result.data == {"server_info": {"host": "demo"}}


def test_servers_get_backend_info_only_collects_backend_info():
    server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"host": "demo"},
        get_backend_status=lambda: {"backend.is_running": True},
    )

    result = servers.get_backend_info(server)

    assert result.success
    assert result.data == {"backend_info": {"backend.is_running": True}}


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


def test_services_browse_service_templates_filters_by_backend():
    docker = SimpleNamespace(
        id="docker",
        backend_capabilities=lambda: {"docker"},
    )
    k8s = SimpleNamespace(
        id="k8s",
        backend_capabilities=lambda: {"kubernetes"},
    )

    result = services.browse_service_templates(
        backends={"docker"},
        list_configs=lambda: [docker, k8s],
    )

    assert result.success
    assert result.data == {"configs": [docker]}


def test_services_build_service_ui_widget_resolves_config_handler():
    service = SimpleNamespace(name="svc")
    bundle = SimpleNamespace()
    widget = object()
    config = SimpleNamespace(
        get_ui_handler=lambda ui, handler: (
            lambda infra, bundle_arg, service_arg: widget
        )
    )
    infra = SimpleNamespace(get_service_config=lambda current: config)

    result = services.build_service_ui_widget(infra, bundle, service)

    assert result.success
    assert result.data == {"widget": widget}


def test_services_build_service_ui_widget_reports_missing_handler():
    service = SimpleNamespace(name="svc")
    config = SimpleNamespace(get_ui_handler=lambda ui, handler: None)
    infra = SimpleNamespace(get_service_config=lambda current: config)

    result = services.build_service_ui_widget(infra, SimpleNamespace(), service)

    assert not result.success
    assert result.message == "Selected service does not provide a TUI view."


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
