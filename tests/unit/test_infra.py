from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from mlox.application import infrastructure_ops as infra_use_cases
from mlox.infra import Bundle, Infrastructure
from mlox.service import AbstractService
from mlox.server import AbstractServer, ServerCapability


@dataclass
class DummyServer(AbstractServer):
    capabilities: ClassVar[set[ServerCapability | str]] = set()

    def setup(self) -> None:
        pass

    def update(self) -> None:
        pass

    def teardown(self) -> None:
        pass

    def get_server_info(self, no_cache: bool = False) -> dict[str, str | int | float]:
        return {}

    def enable_debug_access(self) -> None:
        pass

    def disable_debug_access(self) -> None:
        pass

    def setup_backend(self) -> None:
        pass

    def teardown_backend(self) -> None:
        pass

    def get_backend_status(self) -> dict[str, Any]:
        return {}

    def start_backend_runtime(self) -> None:
        pass

    def stop_backend_runtime(self) -> None:
        pass


class GitServer(DummyServer):
    capabilities: ClassVar[set[ServerCapability | str]] = {ServerCapability.GIT}


class FirewallServer(DummyServer):
    capabilities: ClassVar[set[ServerCapability | str]] = {
        ServerCapability.FIREWALL,
        ServerCapability.NATIVE,
    }


class StringCapabilityServer(DummyServer):
    capabilities: ClassVar[set[ServerCapability | str]] = {"custom_access"}


def make_server(server_cls: type[DummyServer], ip: str) -> DummyServer:
    return server_cls(
        ip=ip,
        root="root",
        root_pw="pw",
        service_config_id="test-server",
    )


class DummyService(AbstractService):
    def setup(self, conn) -> None:
        pass

    def teardown(self, conn) -> None:
        pass

    def check(self, conn) -> dict[str, Any]:
        return {}

    def get_secrets(self) -> dict[str, dict]:
        return {}


def make_service(name: str, config_id: str, uuid: str) -> DummyService:
    service = DummyService(
        name=name,
        service_config_id=config_id,
        template="/tmp/template.yaml",
        target_path="/tmp/service",
    )
    service.uuid = uuid
    return service


def make_infra(*, bundles: list[Bundle] | None = None, configs: dict | None = None) -> Infrastructure:
    infra = Infrastructure.__new__(Infrastructure)
    infra.bundles = bundles or []
    infra.configs = configs or {}
    return infra


def test_filter_server_by_capability_accepts_enum_and_preserves_order():
    first_firewall_server = make_server(FirewallServer, "10.0.0.1")
    git_server = make_server(GitServer, "10.0.0.2")
    second_firewall_server = make_server(FirewallServer, "10.0.0.3")
    infra = Infrastructure()
    infra.bundles = [
        Bundle(name="first-firewall", server=first_firewall_server),
        Bundle(name="git", server=git_server),
        Bundle(name="second-firewall", server=second_firewall_server),
    ]

    assert infra.filter_server_by_capability(ServerCapability.FIREWALL) == [
        first_firewall_server,
        second_firewall_server,
    ]


def test_filter_server_by_capability_accepts_string_capability():
    git_server = make_server(GitServer, "10.0.0.1")
    custom_server = make_server(StringCapabilityServer, "10.0.0.2")
    infra = Infrastructure()
    infra.bundles = [
        Bundle(name="git", server=git_server),
        Bundle(name="custom", server=custom_server),
    ]

    assert infra.filter_server_by_capability("custom_access") == [custom_server]
    assert infra.filter_server_by_capability("GIT") == [git_server]


def test_filter_server_by_capability_returns_empty_list_for_missing_capability():
    infra = Infrastructure()
    infra.bundles = [
        Bundle(name="git", server=make_server(GitServer, "10.0.0.1")),
    ]

    assert infra.filter_server_by_capability(ServerCapability.FIREWALL) == []
    assert infra.filter_server_by_capability("unknown") == []


def test_filter_by_group_supports_global_and_bundle_scoped_queries():
    repo_service = make_service("repo", "repo-config", "svc-repo")
    monitor_service = make_service("monitor", "monitor-config", "svc-monitor")
    dual_service = make_service("dual", "dual-config", "svc-dual")

    repo_bundle = Bundle(name="repo-bundle", server=make_server(GitServer, "10.0.0.1"))
    repo_bundle.services = [repo_service, dual_service]
    monitor_bundle = Bundle(
        name="monitor-bundle",
        server=make_server(FirewallServer, "10.0.0.2"),
    )
    monitor_bundle.services = [monitor_service]

    infra = make_infra(
        bundles=[repo_bundle, monitor_bundle],
        configs={
            "repo-config": SimpleNamespace(groups={"repository": None}),
            "monitor-config": SimpleNamespace(groups={"monitor": None}),
            "dual-config": SimpleNamespace(groups={"repository": None, "monitor": None}),
        },
    )

    assert infra.filter_by_group("repository") == [repo_service, dual_service]
    assert infra.filter_by_group("monitor") == [dual_service, monitor_service]
    assert infra.filter_by_group("repository", bundle=repo_bundle) == [
        repo_service,
        dual_service,
    ]
    assert infra.filter_by_group("repository", bundle=monitor_bundle) == []


def test_infrastructure_lookup_helpers_find_services_bundles_and_servers():
    first_server = make_server(GitServer, "10.0.0.1")
    first_server.uuid = "server-1"
    second_server = make_server(FirewallServer, "10.0.0.2")
    second_server.uuid = "server-2"

    repo_service = make_service("repo", "repo-config", "svc-1")
    monitor_service = make_service("monitor", "monitor-config", "svc-2")

    first_bundle = Bundle(name="first", server=first_server)
    first_bundle.services = [repo_service]
    second_bundle = Bundle(name="second", server=second_server)
    second_bundle.services = [monitor_service]

    infra = make_infra(bundles=[first_bundle, second_bundle])

    assert infra.get_bundle_by_service(repo_service) is first_bundle
    assert infra.get_bundle_by_service(make_service("ghost", "ghost-config", "svc-3")) is None
    assert infra.get_bundle_by_ip("10.0.0.2") is second_bundle
    assert infra.get_bundle_by_ip("10.0.0.99") is None
    assert infra.list_service_names() == ["repo", "monitor"]
    assert list(infra.services()) == [repo_service, monitor_service]
    assert infra.get_service("repo") is repo_service
    assert infra.get_service_by_name("monitor") is monitor_service
    assert infra.get_service("missing") is None
    assert infra.get_service_by_uuid("svc-2") is monitor_service
    assert infra.get_service_by_uuid("missing") is None
    assert infra.get_server_by_uuid("server-1") is first_server
    assert infra.get_server_by_uuid("missing") is None


def test_kubernetes_and_backend_filters_only_return_matching_bundles():
    running_k8s_server = make_server(DummyServer, "10.0.0.1")
    running_k8s_server.backend = ["kubernetes"]
    running_k8s_server.state = "running"

    stopped_k8s_server = make_server(DummyServer, "10.0.0.2")
    stopped_k8s_server.backend = ["kubernetes"]
    stopped_k8s_server.state = "shutdown"

    docker_server = make_server(DummyServer, "10.0.0.3")
    docker_server.backend = ["docker"]
    docker_server.state = "running"

    mixed_server = make_server(DummyServer, "10.0.0.4")
    mixed_server.backend = ["docker", "kubernetes"]
    mixed_server.state = "running"

    running_bundle = Bundle(name="running-k8s", server=running_k8s_server)
    stopped_bundle = Bundle(name="stopped-k8s", server=stopped_k8s_server)
    docker_bundle = Bundle(name="docker", server=docker_server)
    mixed_bundle = Bundle(name="mixed", server=mixed_server)

    infra = make_infra(
        bundles=[running_bundle, stopped_bundle, docker_bundle, mixed_bundle]
    )

    assert infra.list_kubernetes_controller() == [running_bundle, mixed_bundle]
    assert infra.filter_bundles_by_backend("docker") == [docker_bundle, mixed_bundle]
    assert infra.filter_bundles_by_backend("kubernetes") == [
        running_bundle,
        stopped_bundle,
        mixed_bundle,
    ]


def test_to_dict_excludes_configs_from_serialized_payload():
    infra = make_infra(bundles=[], configs={"repo-config": object()})

    payload = infra.to_dict()

    assert payload["bundles"] == []
    assert "configs" not in payload


def test_from_dict_rehydrates_and_populates_runtime_bindings(monkeypatch):
    calls: list[tuple[str, object]] = []
    expected_payload = {"bundles": [{"name": "demo"}]}
    fake_infra = make_infra()

    def fake_populate_configs() -> None:
        calls.append(("populate_configs", fake_infra))

    def fake_populate_registry() -> None:
        calls.append(("populate_service_registry", fake_infra))

    fake_infra.populate_configs = fake_populate_configs
    fake_infra.populate_service_registry = fake_populate_registry

    captured: dict[str, object] = {}

    def fake_dict_to_dataclass(payload, hooks):
        captured["payload"] = payload
        captured["hooks"] = hooks
        return fake_infra

    monkeypatch.setattr("mlox.infra.dict_to_dataclass", fake_dict_to_dataclass)

    result = Infrastructure.from_dict(expected_payload)

    assert result is fake_infra
    assert captured["payload"] == expected_payload
    assert calls == [
        ("populate_configs", fake_infra),
        ("populate_service_registry", fake_infra),
    ]


@pytest.mark.parametrize(
    ("method_name", "patched_name", "args", "expected"),
    [
        ("clear_service_registry", "clear_service_lookups", (), None),
        ("remove_bundle", "remove_bundle", ("bundle",), None),
        ("teardown_service", "teardown_service", ("service",), None),
        ("populate_service_registry", "populate_service_registry", (), None),
        ("populate_configs", "populate_configs", (), None),
        ("get_service_config", "get_service_config", ("service",), "config-result"),
        (
            "add_service",
            "add_service",
            ("10.0.0.1", "config", {"x": "y"}),
            "bundle-result",
        ),
        ("add_server", "add_server", ("config", {"x": "y"}), "server-result"),
    ],
)
def test_infrastructure_methods_delegate_to_application_layer(
    monkeypatch, method_name: str, patched_name: str, args: tuple[object, ...], expected: object
):
    infra = make_infra()
    recorded: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_delegate(*delegate_args, **delegate_kwargs):
        recorded.append((delegate_args, delegate_kwargs))
        return expected

    monkeypatch.setattr(infra_use_cases, patched_name, fake_delegate)

    result = getattr(infra, method_name)(*args)

    if method_name == "add_service":
        assert recorded == [((infra, *args), {"service": None})]
    else:
        assert recorded == [((infra, *args), {})]
    assert result == expected
