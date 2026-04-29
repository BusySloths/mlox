from __future__ import annotations

from types import SimpleNamespace

from mlox.application import infrastructure_ops as infra_use_cases
from mlox.infra import Infrastructure


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _ServerConnectionFactory:
    def __call__(self):
        return _Connection()


class _Service:
    def __init__(self, name: str = "svc", uuid: str = "svc-1"):
        self.name = name
        self.uuid = uuid
        self.calls: list[str] = []
        self.task_executor = None
        self.service_ports = {}
        self._service_lookup = None

    def setup(self, conn) -> None:
        self.calls.append("setup")

    def spin_up(self, conn) -> None:
        self.calls.append("spin_up")

    def spin_down(self, conn) -> None:
        self.calls.append("spin_down")

    def teardown(self, conn) -> None:
        self.calls.append("teardown")

    def set_task_executor(self, executor) -> None:
        self.task_executor = executor

    def bind_service_lookup(self, lookup) -> None:
        self._service_lookup = lookup

    def clear_service_lookup(self) -> None:
        self._service_lookup = None


def test_setup_service_use_case_runs_runtime_steps():
    service = _Service()
    bundle = SimpleNamespace(
        server=SimpleNamespace(get_server_connection=_ServerConnectionFactory()),
    )
    infra = SimpleNamespace(get_bundle_by_service=lambda current: bundle)

    infra_use_cases.setup_service(infra, service)

    assert service.calls == ["setup", "spin_up"]


def test_teardown_service_use_case_clears_lookup_and_removes():
    service = _Service()
    service.bind_service_lookup(object())
    bundle = SimpleNamespace(
        server=SimpleNamespace(get_server_connection=_ServerConnectionFactory()),
        services=[service],
    )
    infra = SimpleNamespace(get_bundle_by_service=lambda current: bundle)

    infra_use_cases.teardown_service(infra, service)

    assert service.calls == ["spin_down", "teardown"]
    assert bundle.services == []
    assert service._service_lookup is None


def test_add_service_use_case_binds_lookup_and_attaches_service(monkeypatch):
    existing = _Service(name="svc")
    created = _Service(name="svc")
    config = SimpleNamespace(
        ports={"http": 8000, "restricted": [22]},
        instantiate_service=lambda params: created,
    )
    server = SimpleNamespace(
        ip="1.2.3.4",
        uuid="server-1",
        mlox_user=SimpleNamespace(name="mlox", home="/home/mlox"),
        create_new_task_executor=lambda: "executor",
    )
    bundle = SimpleNamespace(server=server, services=[existing])
    infra = SimpleNamespace(
        bundles=[bundle],
        configs={},
        list_service_names=lambda: ["svc"],
    )
    monkeypatch.setattr(infra_use_cases, "get_stacks_path", lambda: "/stacks")
    monkeypatch.setattr(infra_use_cases, "generate_username", lambda: "auto-user")
    monkeypatch.setattr(infra_use_cases, "generate_pw", lambda: "auto-pw")
    monkeypatch.setattr(
        infra_use_cases,
        "auto_map_ports",
        lambda used, ports: {"http": 8080},
    )

    result = infra_use_cases.add_service(infra, "1.2.3.4", config, params={})

    assert result is bundle
    assert bundle.services[-1] is created
    assert created.name == "svc_0"
    assert created.task_executor == "executor"
    assert created._service_lookup is infra


def test_bind_service_lookups_binds_all_services():
    service_one = _Service(uuid="a")
    service_two = _Service(uuid="b")
    infra = SimpleNamespace(services=lambda: iter([service_one, service_two]))

    infra_use_cases.bind_service_lookups(infra)

    assert service_one._service_lookup is infra
    assert service_two._service_lookup is infra


def test_add_server_use_case_appends_bundle_and_sets_discovered():
    server = SimpleNamespace(
        ip="1.2.3.4",
        test_connection=lambda: True,
    )
    config = SimpleNamespace(instantiate_server=lambda params: server)
    infra = SimpleNamespace(bundles=[], configs={})

    bundle = infra_use_cases.add_server(infra, config, params={})

    assert bundle is not None
    assert infra.bundles == [bundle]
    assert bundle.server is server
    assert bundle.server.discovered


def test_infrastructure_setup_service_method_remains_compatible(monkeypatch):
    service = _Service()
    infra = Infrastructure.__new__(Infrastructure)
    infra.bundles = []
    infra.configs = {}
    called: list[tuple[object, object]] = []
    monkeypatch.setattr(
        infra_use_cases,
        "setup_service",
        lambda current_infra, current_service: called.append(
            (current_infra, current_service)
        ),
    )

    Infrastructure.setup_service(infra, service)

    assert called == [(infra, service)]
