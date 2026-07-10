from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from mlox.application.result import OperationResult
from mlox.server import ServerCapability
from mlox.application.use_cases import (
    models,
    monitor,
    project,
    repositories,
    secrets,
    servers,
    services,
    workflows,
)
from mlox.service import AbstractService, AbstractWebUIService, ServiceCapability


class _FakeWebUIService(AbstractService, AbstractWebUIService):
    capabilities = {ServiceCapability.WEB_UI}
    web_ui_url_label = "Console"
    web_ui_login_fields = ("username", "password")

    def setup(self, conn):
        pass

    def teardown(self, conn):
        pass

    def check(self, conn):
        return {}

    def get_secrets(self):
        return {}


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


def test_project_rename_workspace_sets_name_and_commits():
    commits = []
    workspace = SimpleNamespace(name="demo")
    workspace.commit = lambda: commits.append(workspace.name)

    result = project.rename_project_workspace(workspace, " renamed demo ")

    assert result.success
    assert workspace.name == "renamed demo"
    assert commits == ["renamed demo"]
    assert result.data == {"workspace": workspace}


def test_project_rename_workspace_rejects_empty_names():
    workspace = SimpleNamespace(name="demo")

    result = project.rename_project_workspace(workspace, "   ")

    assert not result.success
    assert workspace.name == "demo"


def test_project_rename_workspace_restores_name_when_commit_fails():
    workspace = SimpleNamespace(name="demo")
    workspace.commit = lambda: (_ for _ in ()).throw(RuntimeError("disk full"))

    result = project.rename_project_workspace(workspace, "renamed")

    assert not result.success
    assert workspace.name == "demo"
    assert result.message == "Failed to rename project: disk full"


def test_project_rename_bundle_sets_name_and_commits():
    commits = []
    bundle = SimpleNamespace(name="dev")
    workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[bundle]))
    workspace.commit = lambda: commits.append(bundle.name)

    result = project.rename_bundle(workspace, bundle, " renamed dev ")

    assert result.success
    assert bundle.name == "renamed dev"
    assert commits == ["renamed dev"]
    assert result.data == {"workspace": workspace, "bundle": bundle}


def test_project_rename_bundle_rejects_empty_and_duplicate_names():
    bundle = SimpleNamespace(name="dev")
    other_bundle = SimpleNamespace(name="prod")
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(bundles=[bundle, other_bundle])
    )

    empty = project.rename_bundle(workspace, bundle, " ")
    duplicate = project.rename_bundle(workspace, bundle, "PROD")

    assert not empty.success
    assert not duplicate.success
    assert bundle.name == "dev"


def test_project_rename_bundle_restores_name_when_commit_fails():
    bundle = SimpleNamespace(name="dev")
    workspace = SimpleNamespace(infrastructure=SimpleNamespace(bundles=[bundle]))
    workspace.commit = lambda: (_ for _ in ()).throw(RuntimeError("disk full"))

    result = project.rename_bundle(workspace, bundle, "renamed")

    assert not result.success
    assert bundle.name == "dev"
    assert result.message == "Failed to rename bundle: disk full"


def test_project_update_bundle_tags_normalizes_and_commits():
    commits = []
    bundle = SimpleNamespace(name="demo", tags=["old"])
    workspace = SimpleNamespace()
    workspace.commit = lambda: commits.append(list(bundle.tags))

    result = project.update_bundle_tags(
        workspace,
        bundle,
        [" prod ", "gpu", "PROD", "", "critical"],
    )

    assert result.success
    assert bundle.tags == ["prod", "gpu", "critical"]
    assert commits == [["prod", "gpu", "critical"]]
    assert result.data == {
        "workspace": workspace,
        "bundle": bundle,
        "tags": ["prod", "gpu", "critical"],
    }


def test_project_update_bundle_tags_restores_tags_when_commit_fails():
    bundle = SimpleNamespace(name="demo", tags=["old"])
    workspace = SimpleNamespace()
    workspace.commit = lambda: (_ for _ in ()).throw(RuntimeError("disk full"))

    result = project.update_bundle_tags(workspace, bundle, ["new"])

    assert not result.success
    assert bundle.tags == ["old"]
    assert result.message == "Failed to update bundle tags: disk full"


def test_project_summarize_infrastructure_builds_rows_and_resource_totals():
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker"],
        capabilities={ServerCapability.DOCKER, ServerCapability.TERMINAL},
        get_server_info=lambda: {"cpu_count": 8, "ram_gb": 16},
    )
    service = SimpleNamespace(
        name="MLflow",
        service_config_id="mlflow",
        state="running",
    )
    failed_service = SimpleNamespace(
        name="Registry",
        service_config_id="registry",
        state="failed",
    )
    uninitialized_service = SimpleNamespace(
        name="Jobs",
        service_config_id="jobs",
        state="un-initialized",
    )
    pending_service = SimpleNamespace(
        name="Airflow",
        service_config_id="airflow",
        state="pending",
    )
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(
            bundles=[
                SimpleNamespace(
                    name="demo",
                    server=server,
                    services=[
                        service,
                        failed_service,
                        uninitialized_service,
                        pending_service,
                    ],
                )
            ]
        )
    )

    result = project.summarize_infrastructure(workspace)

    assert result.success
    summary = result.data["summary"]
    assert summary["has_data"] is True
    assert summary["totals"] == {
        "bundles": 1,
        "servers": 1,
        "services": 4,
        "cpu": 8.0,
        "ram": 16.0,
    }
    assert summary["server_rows"] == [
        {
            "bundle": "demo",
            "server": "10.0.0.1",
            "backend": "docker",
            "state": "running",
            "services": 4,
            "service_states": {
                "running": 1,
                "error": 1,
                "un-initialized": 1,
                "other": 1,
            },
        }
    ]


def test_secrets_describe_managers_does_not_list_secret_values():
    class SecretManager:
        supports_keyfile_export = True

        def is_working(self):
            return True

    descriptor = SimpleNamespace(
        id="embedded",
        name="Embedded Project Storage",
        kind="embedded",
        service_uuid=None,
        is_active=True,
        is_available=True,
        supports_keyfile_export=True,
        manager=SecretManager(),
        service=None,
    )
    workspace = SimpleNamespace(
        list_secret_managers=lambda: [descriptor],
    )

    result = secrets.describe_secret_managers(workspace)

    assert result.success
    assert result.data["active_manager_id"] == "embedded"
    assert result.data["managers"] == [
        {
            "id": "embedded",
            "name": "Embedded Project Storage",
            "kind": "embedded",
            "service_uuid": None,
            "location": {
                "bundle": "Project",
                "backend": "embedded",
                "service": "",
            },
            "is_active": True,
            "is_available": True,
            "status": "available",
            "class": "SecretManager",
            "supports_keyfile_export": True,
        }
    ]


def test_secrets_list_secret_names_returns_redacted_inventory():
    class SecretManager:
        supports_keyfile_export = True

        def is_working(self):
            return True

        def list_secrets(self, keys_only=False):
            assert keys_only is True
            return {"api-token": None, "db-password": None}

    descriptor = SimpleNamespace(
        id="embedded",
        name="Embedded Project Storage",
        kind="embedded",
        service_uuid=None,
        is_active=True,
        is_available=True,
        supports_keyfile_export=True,
        manager=SecretManager(),
        service=None,
    )
    workspace = SimpleNamespace(probe_secret_manager=lambda manager_id: descriptor)

    result = secrets.list_secret_names(workspace, "embedded")

    assert result.success
    assert result.data["secrets"] == [
        {"name": "api-token", "value": "hidden"},
        {"name": "db-password", "value": "hidden"},
    ]
    assert "secret-value" not in str(result.data)


def test_secrets_describe_managers_includes_service_location():
    service = SimpleNamespace(uuid="service-1", name="Vault")
    server = SimpleNamespace(backend=["docker"])
    bundle = SimpleNamespace(name="prod", server=server, services=[service])
    descriptor = SimpleNamespace(
        id="service-1",
        name="Vault",
        kind="service",
        service_uuid="service-1",
        is_active=False,
        is_available=None,
        supports_keyfile_export=False,
        manager=None,
        service=service,
    )
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(bundles=[bundle]),
        list_secret_managers=lambda: [descriptor],
    )

    result = secrets.describe_secret_managers(workspace)

    assert result.success
    assert result.data["managers"][0]["location"] == {
        "bundle": "prod",
        "backend": "docker",
        "service": "Vault",
    }
    assert result.data["managers"][0]["class"] == "SimpleNamespace"


def test_secrets_reveal_secret_loads_selected_secret_value():
    class SecretManager:
        supports_keyfile_export = False

        def load_secret(self, name):
            return {"token": "secret-value"} if name == "api-token" else None

    descriptor = SimpleNamespace(
        id="embedded",
        name="Embedded Project Storage",
        kind="embedded",
        service_uuid=None,
        is_active=True,
        is_available=True,
        supports_keyfile_export=False,
        manager=SecretManager(),
        service=None,
    )
    workspace = SimpleNamespace(probe_secret_manager=lambda manager_id: descriptor)

    result = secrets.reveal_secret(workspace, "embedded", "api-token")

    assert result.success
    assert result.data["name"] == "api-token"
    assert result.data["value"] == {"token": "secret-value"}


def test_secrets_save_secret_updates_selected_manager():
    class SecretManager:
        supports_keyfile_export = False

        def __init__(self):
            self.store = {}

        def save_secret(self, name, value):
            self.store[name] = value

    manager = SecretManager()
    descriptor = SimpleNamespace(
        id="embedded",
        name="Embedded Project Storage",
        kind="embedded",
        service_uuid=None,
        is_active=True,
        is_available=True,
        supports_keyfile_export=False,
        manager=manager,
        service=None,
    )
    workspace = SimpleNamespace(probe_secret_manager=lambda manager_id: descriptor)

    result = secrets.save_secret(workspace, "embedded", "api-token", {"token": "new"})

    assert result.success
    assert manager.store == {"api-token": {"token": "new"}}
    assert result.data["value"] == {"token": "new"}


def test_secrets_collect_service_secrets_saves_by_service_uuid():
    class SecretManager:
        supports_keyfile_export = False

        def __init__(self):
            self.store = {}

        def save_secret(self, name, value):
            self.store[name] = value

    manager = SecretManager()
    descriptor = SimpleNamespace(
        id="embedded",
        name="Embedded Project Storage",
        kind="embedded",
        service_uuid=None,
        is_active=True,
        is_available=True,
        supports_keyfile_export=False,
        manager=manager,
        service=None,
    )
    service_a = SimpleNamespace(
        uuid="service-a",
        name="MLflow",
        get_secrets=lambda: {"basic_auth": {"password": "secret"}},
    )
    service_b = SimpleNamespace(
        uuid="service-b",
        name="Registry",
        get_secrets=lambda: {"registry": {"token": "token"}},
    )
    workspace = SimpleNamespace(
        probe_secret_manager=lambda manager_id: descriptor,
        infrastructure=SimpleNamespace(
            bundles=[
                SimpleNamespace(services=[service_a]),
                SimpleNamespace(services=[service_b]),
            ]
        ),
    )

    result = secrets.collect_service_secrets(workspace, "embedded")

    assert result.success
    assert manager.store == {
        "service-a": {"basic_auth": {"password": "secret"}},
        "service-b": {"registry": {"token": "token"}},
    }
    assert result.data["service_count"] == 2
    assert result.data["secret_count"] == 2


def test_secrets_collect_service_secrets_reports_service_failures():
    class SecretManager:
        supports_keyfile_export = False

        def __init__(self):
            self.store = {}

        def save_secret(self, name, value):
            self.store[name] = value

    def fail():
        raise RuntimeError("offline")

    manager = SecretManager()
    descriptor = SimpleNamespace(
        id="embedded",
        name="Embedded Project Storage",
        kind="embedded",
        service_uuid=None,
        is_active=True,
        is_available=True,
        supports_keyfile_export=False,
        manager=manager,
        service=None,
    )
    good = SimpleNamespace(
        uuid="good-service",
        name="Good",
        get_secrets=lambda: {"token": "ok"},
    )
    bad = SimpleNamespace(uuid="bad-service", name="Bad", get_secrets=fail)
    workspace = SimpleNamespace(
        probe_secret_manager=lambda manager_id: descriptor,
        infrastructure=SimpleNamespace(bundles=[SimpleNamespace(services=[good, bad])]),
    )

    result = secrets.collect_service_secrets(workspace, "embedded")

    assert result.success
    assert manager.store == {"good-service": {"token": "ok"}}
    assert result.data["service_count"] == 1
    assert result.data["error_count"] == 1
    assert result.data["errors"] == [{"service": "Bad", "error": "offline"}]


def test_secrets_activate_secret_manager_delegates_to_workspace():
    calls = []
    workspace = SimpleNamespace(
        set_secret_manager=lambda manager_id: calls.append(manager_id)
        or OperationResult(True, 0, "updated"),
    )

    result = secrets.activate_secret_manager(workspace, "service-1")

    assert result.success
    assert calls == ["service-1"]


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
    assert result.data == {"bundle": bundle, "server": server}


def test_servers_setup_server_fails_if_server_stays_uninitialized():
    server = SimpleNamespace(
        state="un-initialized",
        setup=lambda: None,
    )
    bundle = SimpleNamespace(server=server)
    current = _project(
        SimpleNamespace(get_bundle_by_ip=lambda ip: bundle if ip == "1.2.3.4" else None)
    )

    result = servers.setup_server(current, ip="1.2.3.4")

    assert not result.success
    assert result.message == (
        "Server 1.2.3.4 setup did not complete; server is still un-initialized."
    )
    assert result.data == {"bundle": bundle, "server": server}


def test_servers_setup_server_retries_runtime_backend_setup_when_backend_is_down():
    calls = []
    backend_statuses = [
        {"backend.is_running": False},
        {"backend.is_running": True},
    ]
    server = SimpleNamespace(
        state="running",
        backend=["kubernetes", "k3s"],
        setup=lambda: calls.append("setup"),
        setup_backend=lambda: calls.append("setup_backend"),
        get_backend_status=lambda: backend_statuses.pop(0),
    )
    bundle = SimpleNamespace(server=server)
    current = _project(
        SimpleNamespace(get_bundle_by_ip=lambda ip: bundle if ip == "1.2.3.4" else None)
    )

    result = servers.setup_server(current, ip="1.2.3.4")

    assert result.success
    assert calls == ["setup", "setup_backend"]
    assert result.data == {"bundle": bundle, "server": server}


def test_servers_setup_server_fails_when_runtime_backend_remains_down():
    server = SimpleNamespace(
        state="running",
        backend=["kubernetes", "k3s"],
        setup=lambda: None,
        setup_backend=lambda: None,
        get_backend_status=lambda: {"backend.is_running": False},
    )
    bundle = SimpleNamespace(server=server)
    current = _project(
        SimpleNamespace(get_bundle_by_ip=lambda ip: bundle if ip == "1.2.3.4" else None)
    )

    result = servers.setup_server(current, ip="1.2.3.4")

    assert not result.success
    assert result.message == "Server 1.2.3.4 setup completed, but backend is not running."
    assert result.data == {
        "backend_status": {"backend.is_running": False},
        "bundle": bundle,
        "server": server,
    }


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


def test_servers_resolve_server_template_setup_uses_tui_handler():
    setup = object()
    config = SimpleNamespace(get_ui_handler=lambda ui, handler: lambda infra, cfg: setup)

    result = servers.resolve_server_template_setup(SimpleNamespace(), config)

    assert result.success
    assert result.data == {"setup": setup}


def test_servers_resolve_server_template_setup_reports_missing_handler():
    config = SimpleNamespace(get_ui_handler=lambda ui, handler: None)

    result = servers.resolve_server_template_setup(SimpleNamespace(), config)

    assert not result.success
    assert result.message == "Selected server template does not provide a TUI setup form."


def test_servers_add_server_from_template_delegates_to_workspace():
    calls = []
    result = SimpleNamespace(success=True, message="ok")
    workspace = SimpleNamespace(
        add_server_from_config=lambda config, params: (
            calls.append((config, params)) or result
        )
    )
    config = SimpleNamespace(id="server-template")
    params = {"${MLOX_IP}": "127.0.0.1"}

    actual = servers.add_server_from_template(workspace, config, params)

    assert actual is result
    assert calls == [(config, params)]


def test_servers_setup_bundle_delegates_to_workspace_and_returns_bundle():
    calls = []
    result = SimpleNamespace(success=True, message="setup", data={})
    workspace = SimpleNamespace(setup_server=lambda ip: calls.append(ip) or result)
    bundle = SimpleNamespace(server=SimpleNamespace(ip="1.2.3.4"))

    actual = servers.setup_bundle(workspace, bundle)

    assert actual is result
    assert calls == ["1.2.3.4"]
    assert result.data == {"bundle": bundle}


def test_servers_setup_bundle_uses_current_workspace_bundle_after_ip_changes():
    calls = []
    missing = OperationResult(False, 5, "Server not found in infrastructure.")
    result = OperationResult(True, 0, "setup", {})
    stale_bundle = SimpleNamespace(server=SimpleNamespace(ip="mlox-vm", uuid="srv-1"))
    current_bundle = SimpleNamespace(server=SimpleNamespace(ip="10.0.64.12", uuid="srv-1"))

    def setup_server(ip: str):
        calls.append(ip)
        return result if ip == "10.0.64.12" else missing

    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(bundles=[current_bundle]),
        setup_server=setup_server,
    )

    actual = servers.setup_bundle(workspace, stale_bundle)

    assert actual is result
    assert calls == ["mlox-vm", "10.0.64.12"]
    assert result.data == {"bundle": current_bundle}


def test_servers_remove_bundle_delegates_to_workspace():
    calls = []
    result = SimpleNamespace(success=True, message="removed", data={})
    workspace = SimpleNamespace(teardown_server=lambda ip: calls.append(ip) or result)
    bundle = SimpleNamespace(server=SimpleNamespace(ip="1.2.3.4"))

    actual = servers.remove_bundle(workspace, bundle)

    assert actual is result
    assert calls == ["1.2.3.4"]


def test_servers_open_server_terminal_uses_launcher():
    launched = []
    server = SimpleNamespace(
        ip="1.2.3.4",
        capabilities={ServerCapability.TERMINAL},
        get_server_connection=lambda: SimpleNamespace(
            credentials={"host": "1.2.3.4", "port": 22, "user": "mlox"}
        ),
    )

    result = servers.open_server_terminal(server, launcher=launched.append)

    assert result.success
    assert launched == [server]
    assert result.message == "Opened SSH terminal for 1.2.3.4."


def test_servers_terminal_capability_rejects_connector_servers():
    server = SimpleNamespace(
        ip="connector",
        capabilities={"connector"},
        get_server_connection=lambda: SimpleNamespace(credentials={}),
    )

    result = servers.can_open_server_terminal(server)

    assert not result.success
    assert result.message == "The selected server does not support terminal login."


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


def test_services_rename_service_validates_and_updates_name():
    service = SimpleNamespace(name="svc")
    infra = SimpleNamespace(
        get_service=lambda name: service if service.name == name else None,
        list_service_names=lambda: [service.name, "existing"],
    )
    current = _project(infra)

    empty = services.rename_service(current, name="svc", new_name=" ")
    duplicate = services.rename_service(current, name="svc", new_name="existing")
    renamed = services.rename_service(current, name="svc", new_name="renamed")

    assert not empty.success
    assert empty.message == "Service name must not be empty."
    assert not duplicate.success
    assert duplicate.message == "Service name must be unique."
    assert renamed.success
    assert service.name == "renamed"


def test_services_teardown_service_runs_runtime_steps_and_removes_service():
    calls = []
    service = SimpleNamespace(
        name="svc",
        state="running",
        spin_down=lambda conn: calls.append("spin_down"),
        teardown=lambda conn: calls.append("teardown"),
        clear_service_lookup=lambda: calls.append("clear_lookup"),
    )
    bundle = SimpleNamespace(
        server=SimpleNamespace(get_server_connection=lambda: _Connection()),
        services=[service],
    )
    current = _project(
        SimpleNamespace(
            get_service=lambda name: service if name == "svc" else None,
            get_bundle_by_service=lambda value: bundle if value is service else None,
        )
    )

    result = services.teardown_service(current, name="svc")

    assert result.success
    assert calls == ["spin_down", "teardown", "clear_lookup"]
    assert bundle.services == []


def test_services_teardown_uninitialized_service_removes_without_runtime_steps():
    calls = []
    service = SimpleNamespace(
        name="svc",
        state="un-initialized",
        spin_down=lambda conn: calls.append("spin_down"),
        teardown=lambda conn: calls.append("teardown"),
        clear_service_lookup=lambda: calls.append("clear_lookup"),
    )
    bundle = SimpleNamespace(
        server=SimpleNamespace(
            get_server_connection=lambda: (_ for _ in ()).throw(
                AssertionError("connection should not be opened")
            )
        ),
        services=[service],
    )
    current = _project(
        SimpleNamespace(
            get_service=lambda name: service if name == "svc" else None,
            get_bundle_by_service=lambda value: bundle if value is service else None,
        )
    )

    result = services.teardown_service(current, name="svc")

    assert result.success
    assert calls == ["clear_lookup"]
    assert bundle.services == []


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


def test_services_template_setup_resolves_handler_and_materializes_params():
    setup = SimpleNamespace(
        params=lambda values, infra: {"${NAME}": values["name"]},
    )
    config = SimpleNamespace(
        get_ui_handler=lambda ui, handler: (
            lambda infra, bundle, config_arg: setup
        )
    )

    resolved = services.resolve_service_template_setup(
        SimpleNamespace(),
        SimpleNamespace(),
        config,
    )
    materialized = services.materialize_service_template_params(
        setup,
        {"name": "svc"},
        SimpleNamespace(),
    )

    assert resolved.success
    assert resolved.data == {"setup": setup}
    assert materialized.success
    assert materialized.data == {"params": {"${NAME}": "svc"}}


def test_services_add_service_from_template_delegates_to_workspace():
    calls = []
    config = SimpleNamespace(id="svc-template")
    bundle = SimpleNamespace(server=SimpleNamespace(ip="10.0.0.5"))
    workspace = SimpleNamespace(
        add_service_from_config=lambda config_arg, **kwargs: (
            calls.append((config_arg, kwargs))
            or OperationResult(True, 0, "added")
        )
    )

    result = services.add_service_from_template(
        workspace,
        bundle,
        config,
        {"${X}": "y"},
    )

    assert result.success
    assert calls == [
        (
            config,
            {
                "server_ip": "10.0.0.5",
                "params": {"${X}": "y"},
            },
        )
    ]


def test_services_setup_service_in_workspace_delegates_by_name():
    calls = []
    service = SimpleNamespace(name="svc")
    workspace = SimpleNamespace(
        setup_service=lambda **kwargs: (
            calls.append(kwargs)
            or OperationResult(True, 0, "setup")
        )
    )

    result = services.setup_service_in_workspace(workspace, service)

    assert result.success
    assert calls == [{"name": "svc"}]


def test_services_teardown_service_in_workspace_delegates_by_name():
    calls = []
    service = SimpleNamespace(name="svc")
    workspace = SimpleNamespace(
        teardown_service=lambda **kwargs: (
            calls.append(kwargs)
            or OperationResult(True, 0, "teardown")
        )
    )

    result = services.teardown_service_in_workspace(workspace, service)

    assert result.success
    assert calls == [{"name": "svc"}]


def test_services_rename_service_in_workspace_delegates_by_name():
    calls = []
    service = SimpleNamespace(name="svc")
    workspace = SimpleNamespace(
        rename_service=lambda **kwargs: (
            calls.append(kwargs)
            or OperationResult(True, 0, "renamed")
        )
    )

    result = services.rename_service_in_workspace(workspace, service, "new")

    assert result.success
    assert calls == [{"name": "svc", "new_name": "new"}]


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


def test_services_web_ui_address_requires_capability_and_url():
    missing = SimpleNamespace(name="api")
    capable_without_url = SimpleNamespace(
        name="ui",
        capabilities={ServiceCapability.WEB_UI},
        get_web_ui_address=lambda: "",
    )
    capable = SimpleNamespace(
        name="ui",
        capabilities={ServiceCapability.WEB_UI},
        get_web_ui_address=lambda: "https://example.test/ui",
    )

    no_capability = services.get_service_web_ui_address(missing)
    no_url = services.get_service_web_ui_address(capable_without_url)
    result = services.get_service_web_ui_address(capable)

    assert not no_capability.success
    assert no_capability.message == "Selected service does not provide a web UI."
    assert not no_url.success
    assert "Set up the service first" in no_url.message
    assert result.success
    assert result.data == {"url": "https://example.test/ui"}


def test_web_ui_service_prefers_configured_url_label():
    service = _FakeWebUIService(
        name="ui",
        service_config_id="web-ui",
        template="/tmp/template",
        target_path="/tmp/target",
    )
    service.service_urls["API"] = "https://example.test/api"
    service.service_urls["Console"] = "https://example.test/console"

    result = services.get_service_web_ui_address(service)

    assert result.success
    assert result.data == {"url": "https://example.test/console"}


def test_services_web_ui_login_value_resolves_requested_field():
    service = _FakeWebUIService(
        name="ui",
        service_config_id="web-ui",
        template="/tmp/template",
        target_path="/tmp/target",
    )
    service.ui_user = "admin"
    service.ui_pw = "secret"

    fields = services.list_service_web_ui_login_fields(service)
    password = services.get_service_web_ui_login_value(service, "password")

    assert fields.success
    assert fields.data == {"fields": ["username", "password"]}
    assert password.success
    assert password.data == {"field": "password", "value": "secret"}


def test_services_open_service_web_ui_uses_injected_opener():
    opened = []
    service = SimpleNamespace(
        name="ui",
        capabilities={ServiceCapability.WEB_UI},
        get_web_ui_address=lambda: "https://example.test/ui",
    )

    result = services.open_service_web_ui(service, opener=opened.append)

    assert result.success
    assert opened == ["https://example.test/ui"]


def test_monitor_describe_monitoring_collects_monitor_service_rows():
    service = SimpleNamespace(
        name="otel",
        state="running",
        capabilities={ServiceCapability.MONITOR},
        get_monitor_snapshot=lambda bundle: {
            "cpu_used_ratio": 0.4,
            "ram_free_ratio": 0.7,
            "disk_free_ratio": 0.8,
            "network_in_rate": 2048,
            "network_out_rate": 1024,
            "network_unit": "By",
            "metric_points": 12,
        },
    )
    bundle = SimpleNamespace(
        name="prod",
        server=SimpleNamespace(ip="10.0.0.5"),
        services=[service],
    )
    infra = SimpleNamespace(bundles=[bundle])

    result = monitor.describe_monitoring(infra)

    assert result.success
    assert result.data["rows"][0]["bundle"] == "prod"
    assert result.data["rows"][0]["service"] == "otel"
    assert result.data["rows"][0]["cpu_used_ratio"] == 0.4
    assert result.data["rows"][0]["metric_points"] == 12


def test_monitor_describe_monitoring_reports_snapshot_failures():
    def fail(_bundle):
        raise RuntimeError("collector unavailable")

    service = SimpleNamespace(
        name="otel",
        state="running",
        capabilities={"monitor"},
        get_monitor_snapshot=fail,
    )
    bundle = SimpleNamespace(
        name="prod",
        server=SimpleNamespace(ip="10.0.0.5"),
        services=[service],
    )

    result = monitor.describe_monitoring(SimpleNamespace(bundles=[bundle]))

    assert result.success
    assert result.data["rows"][0]["message"] == (
        "Failed to load monitor metrics: collector unavailable"
    )


def test_workflows_describe_workflows_collects_orchestrators_and_dags():
    service = SimpleNamespace(
        uuid="airflow-1",
        name="Airflow",
        service_config_id="airflow",
        state="running",
        service_urls={"Airflow UI": "https://example.test:8080"},
        capabilities={ServiceCapability.WORKFLOW_ORCHESTRATOR},
        list_workflows=lambda: [
            {
                "id": "daily_train",
                "name": "daily_train",
                "schedule": "@daily",
                "is_paused": False,
                "is_active": True,
                "owners": "ml",
                "last_run_state": "success",
            },
            {
                "id": "batch_score",
                "name": "batch_score",
                "schedule": "0 * * * *",
                "is_paused": True,
                "is_active": True,
            },
        ],
    )
    bundle = SimpleNamespace(
        name="prod",
        server=SimpleNamespace(ip="10.0.0.5"),
        services=[service],
    )
    infra = SimpleNamespace(bundles=[bundle])

    result = workflows.describe_workflows(infra)

    assert result.success
    assert result.data["metrics"] == {
        "orchestrators": 1,
        "running_orchestrators": 1,
        "workflows": 2,
        "active_workflows": 2,
        "paused_workflows": 1,
    }
    assert result.data["orchestrators"][0]["workflow_count"] == 2
    assert result.data["workflows_by_orchestrator"]["airflow-1"][0]["name"] == (
        "daily_train"
    )


def test_workflows_describe_workflows_reports_list_failures():
    def fail():
        raise RuntimeError("api unavailable")

    service = SimpleNamespace(
        uuid="airflow-1",
        name="Airflow",
        state="running",
        capabilities={"workflow_orchestrator"},
        list_workflows=fail,
    )
    bundle = SimpleNamespace(
        name="prod",
        server=SimpleNamespace(ip="10.0.0.5"),
        services=[service],
    )

    result = workflows.describe_workflows(SimpleNamespace(bundles=[bundle]))

    assert result.success
    assert result.data["orchestrators"][0]["message"] == (
        "Failed to load workflows: api unavailable"
    )
    assert result.data["workflows_by_orchestrator"]["airflow-1"] == []


def _repository_workspace(service, *, commit_calls=None):
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_connection=lambda: _Connection(),
    )
    bundle = SimpleNamespace(name="dev", server=server, services=[service])
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(bundles=[bundle]),
        commit=lambda: commit_calls.append("commit")
        if commit_calls is not None
        else None,
    )
    return workspace, bundle


def _repository_service(**overrides):
    service = SimpleNamespace(
        uuid="repo-1",
        name="Repo",
        repo_name="demo",
        state="running",
        capabilities={ServiceCapability.REPOSITORY},
        is_private=False,
        cloned=False,
        get_url=lambda: "https://github.com/acme/demo",
        get_repository_root=lambda: "/repos/demo",
        repository_summary=lambda: {
            "name": "demo",
            "url": "https://github.com/acme/demo",
            "root": "/repos/demo",
            "private": False,
            "cloned": False,
            "state": "running",
            "created": "",
            "modified": "",
            "deploy_keys_available": False,
        },
        get_deploy_keys=lambda: {},
        check=lambda conn: {"cloned": False, "exists": False, "private": False},
        list_repository_tree=lambda conn: [],
        read_repository_file=lambda conn, path: "content",
    )
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def test_repositories_describe_finds_repository_services():
    service = _repository_service()
    workspace, _ = _repository_workspace(service)

    result = repositories.describe_repositories(workspace.infrastructure)

    assert result.success
    assert result.data["metrics"]["total"] == 1
    assert result.data["repositories"][0]["id"] == "repo-1"
    assert result.data["repositories"][0]["bundle"] == "dev"
    assert result.data["repositories"][0]["server"] == "10.0.0.5"
    assert result.data["repositories"][0]["url"] == "https://github.com/acme/demo"


def test_repositories_get_deploy_keys_returns_private_keys_and_empty_public_keys():
    private = _repository_service(
        is_private=True,
        get_deploy_keys=lambda: {"public": "ssh-rsa AAA"},
    )
    private_workspace, _ = _repository_workspace(private)
    public = _repository_service(get_deploy_keys=lambda: {})
    public_workspace, _ = _repository_workspace(public)

    private_result = repositories.get_repository_deploy_keys(
        private_workspace, "repo-1"
    )
    public_result = repositories.get_repository_deploy_keys(public_workspace, "repo-1")

    assert private_result.success
    assert private_result.data["keys"] == {"public": "ssh-rsa AAA"}
    assert public_result.success
    assert public_result.data["keys"] == {}


def test_repositories_clone_and_pull_call_service_methods_and_commit():
    calls = []
    commits = []
    service = _repository_service()
    service.git_clone = lambda conn: calls.append("clone")
    service.git_pull = lambda conn: calls.append("pull")
    workspace, _ = _repository_workspace(service, commit_calls=commits)

    clone_result = repositories.clone_repository(workspace, "repo-1")
    pull_result = repositories.pull_repository(workspace, "repo-1")

    assert clone_result.success
    assert pull_result.success
    assert calls == ["clone", "pull"]
    assert commits == ["commit", "commit"]


def test_repositories_clone_failure_reports_error_and_does_not_commit():
    commits = []
    service = _repository_service()

    def fail_clone(conn):
        raise RuntimeError(
            "Private GitHub repository clone failed. Use Copy Deploy Keys."
        )

    service.git_clone = fail_clone
    workspace, _ = _repository_workspace(service, commit_calls=commits)

    result = repositories.clone_repository(workspace, "repo-1")

    assert not result.success
    assert "Copy Deploy Keys" in result.message
    assert commits == []


def test_repositories_refresh_normalizes_tree_and_filters_git():
    service = _repository_service(
        check=lambda conn: {"cloned": True, "exists": True, "private": False},
        list_repository_tree=lambda conn: [
            {"name": "demo", "path": "/repos/demo", "is_dir": True, "size": 0},
            {"name": ".git", "path": "/repos/demo/.git", "is_dir": True, "size": 0},
            {
                "name": "config",
                "path": "/repos/demo/.git/config",
                "is_file": True,
                "size": 12,
            },
            {
                "name": "app.py",
                "path": "/repos/demo/src/app.py",
                "is_file": True,
                "size": 20,
                "modification_datetime": "2026-01-01 10:00:00",
            },
        ],
    )
    workspace, _ = _repository_workspace(service)

    result = repositories.refresh_repository(workspace, "repo-1")

    assert result.success
    assert result.data["tree"] == [
        {
            "name": "app.py",
            "path": "/repos/demo/src/app.py",
            "display_path": "src/app.py",
            "is_file": True,
            "is_dir": False,
            "size": 20,
            "modification_datetime": "2026-01-01 10:00:00",
        }
    ]


def test_repositories_refresh_skips_tree_for_uncloned_repositories():
    calls = []
    service = _repository_service(
        check=lambda conn: {"cloned": False, "exists": False, "private": False},
        list_repository_tree=lambda conn: calls.append("tree"),
    )
    workspace, _ = _repository_workspace(service)

    result = repositories.refresh_repository(workspace, "repo-1")
    read_result = repositories.read_repository_file(
        workspace,
        "repo-1",
        "/repos/demo/README.md",
    )

    assert result.success
    assert result.data["tree"] == []
    assert result.data["repository"]["cloned"] is False
    assert result.data["repository"]["message"] == "Repository is not cloned yet."
    assert not read_result.success
    assert read_result.message == "Repository is not cloned yet."
    assert calls == []


def test_repositories_read_file_validates_path_directory_and_size():
    service = _repository_service(
        check=lambda conn: {"cloned": True, "exists": True, "private": False},
        list_repository_tree=lambda conn: [
            {"name": "src", "path": "/repos/demo/src", "is_dir": True, "size": 0},
            {
                "name": "small.py",
                "path": "/repos/demo/src/small.py",
                "is_file": True,
                "size": 5,
            },
            {
                "name": "large.bin",
                "path": "/repos/demo/large.bin",
                "is_file": True,
                "size": 999,
            },
        ],
        read_repository_file=lambda conn, path: "print('ok')",
    )
    workspace, _ = _repository_workspace(service)

    outside = repositories.read_repository_file(workspace, "repo-1", "/tmp/file")
    directory = repositories.read_repository_file(workspace, "repo-1", "/repos/demo/src")
    large = repositories.read_repository_file(
        workspace,
        "repo-1",
        "/repos/demo/large.bin",
        max_bytes=10,
    )
    small = repositories.read_repository_file(
        workspace,
        "repo-1",
        "/repos/demo/src/small.py",
    )

    assert not outside.success
    assert not directory.success
    assert not large.success
    assert small.success
    assert small.data["content"] == "print('ok')"


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


def test_models_describe_model_operations_links_registry_endpoints_and_models():
    registry = SimpleNamespace(
        uuid="registry-1",
        name="MLflow",
        service_config_id="mlflow",
        state="running",
        list_models=lambda filter=None: [
            {"Model": "Demo", "Version": "1", "Status": "READY"}
        ],
    )
    endpoint = SimpleNamespace(
        uuid="endpoint-1",
        name="Demo endpoint",
        service_config_id="mlserver",
        state="running",
        service_url="https://endpoint",
        get_registry=lambda: registry,
        list_supported_models=lambda: [
            {
                "name": "Demo",
                "version": "1",
                "type": "MLServer",
                "status": "running",
            }
        ],
        get_example=lambda model=None, input_example=None: "curl https://endpoint",
    )
    registry_bundle = SimpleNamespace(
        name="registry-bundle",
        server=SimpleNamespace(ip="10.0.0.1"),
        services=[registry],
    )
    endpoint_bundle = SimpleNamespace(
        name="endpoint-bundle",
        server=SimpleNamespace(ip="10.0.0.2"),
        services=[endpoint],
    )
    infra = SimpleNamespace(
        filter_by_group=lambda group: {
            "model-registry": [registry],
            "model-server": [endpoint],
        }.get(group, []),
        get_bundle_by_service=lambda service: registry_bundle
        if service is registry
        else endpoint_bundle,
    )

    result = models.describe_model_operations(infra)

    assert result.success
    assert result.data["registries"][0]["name"] == "MLflow"
    assert result.data["endpoints"][0]["registry_id"] == "registry-1"
    assert result.data["models_by_endpoint"]["endpoint-1"][0]["name"] == "Demo"
    assert "examples_by_endpoint" not in result.data
    assert "examples_by_model" not in result.data
    example_result = models.build_model_example(
        result.data["endpoints"][0],
        result.data["models_by_endpoint"]["endpoint-1"][0],
    )
    assert example_result.success
    assert example_result.data["example"] == "curl https://endpoint"


def test_models_describe_model_operations_does_not_load_input_example_artifacts():
    artifact_calls = []
    registry = SimpleNamespace(
        uuid="registry-1",
        name="MLflow",
        service_config_id="mlflow",
        state="running",
        list_models=lambda filter=None: [],
        load_artifact=lambda *args: artifact_calls.append(args),
    )
    endpoint = SimpleNamespace(
        uuid="endpoint-1",
        name="Demo endpoint",
        service_config_id="mlserver",
        state="running",
        service_url="https://endpoint",
        get_registry=lambda: registry,
        list_supported_models=lambda: [
            {
                "name": "Demo",
                "version": "1",
                "type": "MLServer",
                "status": "running",
            }
        ],
        get_example=lambda model=None, input_example=None: "curl https://endpoint",
    )
    bundle = SimpleNamespace(
        name="bundle",
        server=SimpleNamespace(ip="10.0.0.2"),
        services=[registry, endpoint],
    )
    infra = SimpleNamespace(
        filter_by_group=lambda group: {
            "model-registry": [registry],
            "model-server": [endpoint],
        }.get(group, []),
        get_bundle_by_service=lambda service: bundle,
    )

    result = models.describe_model_operations(infra)

    assert result.success
    assert artifact_calls == []


def test_models_build_model_example_uses_registry_input_example_artifact():
    input_example = {"columns": ["x"], "data": [[1.0]]}
    artifact_calls = []

    def load_artifact(model_name, model_version, artifact_path):
        artifact_calls.append((model_name, model_version, artifact_path))
        return input_example if artifact_path == "input_example.json" else None

    registry = SimpleNamespace(
        uuid="registry-1",
        name="MLflow",
        service_config_id="mlflow",
        state="running",
        list_models=lambda filter=None: [],
        load_artifact=load_artifact,
    )

    def get_example(model=None, input_example=None):
        return f"curl payload={input_example}"

    endpoint = SimpleNamespace(
        uuid="endpoint-1",
        name="Demo endpoint",
        service_config_id="mlserver",
        state="running",
        service_url="https://endpoint",
        get_registry=lambda: registry,
        list_supported_models=lambda: [
            {
                "name": "Demo",
                "version": "1",
                "type": "MLServer",
                "status": "running",
            }
        ],
        get_example=get_example,
    )
    bundle = SimpleNamespace(
        name="bundle",
        server=SimpleNamespace(ip="10.0.0.2"),
        services=[registry, endpoint],
    )
    infra = SimpleNamespace(
        filter_by_group=lambda group: {
            "model-registry": [registry],
            "model-server": [endpoint],
        }.get(group, []),
        get_bundle_by_service=lambda service: bundle,
    )

    describe_result = models.describe_model_operations(infra)
    result = models.build_model_example(
        describe_result.data["endpoints"][0],
        describe_result.data["models_by_endpoint"]["endpoint-1"][0],
    )

    assert describe_result.success
    assert result.success
    assert artifact_calls == [("Demo", "1", "input_example.json")]
    assert result.data["example"] == "curl payload={'columns': ['x'], 'data': [[1.0]]}"


def test_models_call_model_example_posts_generated_curl(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = '{"ok": true}'

        def json(self):
            return {"ok": True}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(models.requests, "post", post)
    example = "\n".join(
        [
            "curl -k -u 'user:pw' \\",
            "  https://endpoint.example/invocations \\",
            "  -H 'Content-Type: application/json' \\",
            """  -d '{"instances": [[1.0]]}'""",
        ]
    )

    result = models.call_model_example(example)

    assert result.success
    assert result.data["body"] == '{\n  "ok": true\n}'
    assert calls == [
        (
            "https://endpoint.example/invocations",
            {
                "headers": {"Content-Type": "application/json"},
                "data": '{"instances": [[1.0]]}',
                "auth": ("user", "pw"),
                "verify": False,
                "timeout": 60,
            },
        )
    ]


def test_models_describe_model_operations_adds_standalone_registry_group():
    endpoint = SimpleNamespace(
        uuid="endpoint-1",
        name="Ollama",
        service_config_id="ollama",
        state="running",
        service_urls={"API": "https://ollama"},
        get_registry=lambda: None,
        list_supported_models=lambda: [
            {"name": "tinyllama", "version": "-", "type": "Ollama", "status": "running"}
        ],
        get_example=lambda model=None, input_example=None: "curl https://ollama",
    )
    bundle = SimpleNamespace(
        name="llm",
        server=SimpleNamespace(ip="10.0.0.3"),
        services=[endpoint],
    )
    infra = SimpleNamespace(
        filter_by_group=lambda group: [endpoint] if group == "model-server" else [],
        get_bundle_by_service=lambda service: bundle,
    )

    result = models.describe_model_operations(infra)

    assert result.success
    assert result.data["registries"][0]["name"] == "Standalone Endpoints"
    assert result.data["endpoints"][0]["registry_id"] == models.STANDALONE_REGISTRY_ID
