from dataclasses import dataclass
from typing import Any, ClassVar

from mlox.infra import Bundle, Infrastructure
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
