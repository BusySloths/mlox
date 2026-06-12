from __future__ import annotations

from types import SimpleNamespace

from mlox.application.use_cases import servers, services
from mlox.infra import Infrastructure
from mlox.project.state import WorkspaceState


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Service:
    def __init__(self, name="svc"):
        self.name = name
        self.calls = []
        self.service_ports = {}
        self._service_lookup = None

    def setup(self, conn):
        self.calls.append("setup")

    def spin_up(self, conn):
        self.calls.append("spin_up")

    def spin_down(self, conn):
        self.calls.append("spin_down")

    def teardown(self, conn):
        self.calls.append("teardown")

    def set_task_executor(self, executor):
        self.executor = executor

    def bind_service_lookup(self, lookup):
        self._service_lookup = lookup

    def clear_service_lookup(self):
        self._service_lookup = None


def test_teardown_service_clears_lookup_and_removes():
    service = _Service()
    service.bind_service_lookup(object())
    bundle = SimpleNamespace(
        server=SimpleNamespace(get_server_connection=lambda: _Connection()),
        services=[service],
    )
    infra = SimpleNamespace(
        get_service=lambda name: service,
        get_bundle_by_service=lambda current: bundle,
    )

    result = services.teardown_service(
        SimpleNamespace(infrastructure=infra),
        name="svc",
    )

    assert result.success
    assert service.calls == ["spin_down", "teardown"]
    assert bundle.services == []
    assert service._service_lookup is None


def test_add_service_binds_lookup_and_attaches_service(monkeypatch):
    created = _Service()
    config = SimpleNamespace(
        id="config",
        ports={"http": 8000, "restricted": [22]},
        instantiate_service=lambda params: created,
    )
    server = SimpleNamespace(
        ip="1.2.3.4",
        uuid="server-1",
        mlox_user=SimpleNamespace(name="mlox", home="/home/mlox"),
        create_new_task_executor=lambda: "executor",
    )
    bundle = SimpleNamespace(server=server, services=[])
    infra = SimpleNamespace(
        bundles=[bundle],
        configs={},
        get_bundle_by_ip=lambda ip: bundle,
        list_service_names=lambda: [],
    )
    monkeypatch.setattr(services, "get_stacks_path", lambda: "/stacks")
    monkeypatch.setattr(services, "generate_username", lambda: "auto-user")
    monkeypatch.setattr(services, "generate_pw", lambda: "auto-pw")
    monkeypatch.setattr(services, "auto_map_ports", lambda used, ports: {"http": 8080})

    result = services.add_service(
        SimpleNamespace(infrastructure=infra),
        lambda template_id: config,
        server_ip=server.ip,
        template_id=config.id,
    )

    assert result.success
    assert bundle.services == [created]
    assert created.executor == "executor"
    assert created._service_lookup is infra


def test_add_server_appends_bundle_and_sets_discovered():
    server = SimpleNamespace(ip="1.2.3.4", test_connection=lambda: True)
    config = SimpleNamespace(
        id="server-config",
        instantiate_server=lambda params: server,
    )
    infra = Infrastructure.__new__(Infrastructure)
    infra.bundles = []
    infra.configs = {}
    infra.get_bundle_by_ip = lambda ip: None
    current = WorkspaceState(name="demo", infrastructure=infra)

    result = servers.add_server(
        current,
        lambda path: config,
        template_path="server.yaml",
        ip=server.ip,
        port=22,
        root_user="root",
        root_password="pw",
    )

    assert result.success
    assert infra.bundles[0].server is server
    assert server.discovered
