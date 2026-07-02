from __future__ import annotations

from types import SimpleNamespace

from mlox.application.use_cases.firewall import (
    collect_firewall_ports,
    describe_project_firewalls,
    enable_bundle_firewall,
    enable_bundle_firewall_with_options,
)
from mlox.server import ServerCapability


class FakeFirewallServer:
    uuid = "server-1"
    ip = "10.0.0.1"
    port = 2222
    state = "running"
    capabilities = {ServerCapability.FIREWALL}

    def __init__(self) -> None:
        self.enabled_ports: list[int] = []
        self.source_ips_by_port = None
        self.status = "Status: inactive"

    def firewall_status(self):
        return self.status

    def firewall_up(self, ports, source_ips_by_port=None):
        self.enabled_ports = list(ports)
        self.source_ips_by_port = source_ips_by_port
        self.status = (
            "Status: active\n"
            + "\n".join(
                f"-A MLOX-FIREWALL -p tcp -m tcp --dport {port} -j ACCEPT"
                for port in ports
            )
        )


def test_collect_firewall_ports_includes_ssh_and_service_ports() -> None:
    server = FakeFirewallServer()
    service = SimpleNamespace(name="MLflow", service_ports={"http": 5000})
    bundle = SimpleNamespace(name="demo", server=server, services=[service])

    ports = collect_firewall_ports(bundle)

    assert ports == [2222, 5000]


def test_enable_bundle_firewall_uses_recommended_ports_including_ssh() -> None:
    server = FakeFirewallServer()
    service = SimpleNamespace(name="MLflow", service_ports={"http": 5000})
    bundle = SimpleNamespace(name="demo", server=server, services=[service])

    result = enable_bundle_firewall(bundle)

    assert result.success
    assert server.enabled_ports == [2222, 5000]
    assert result.data["firewall"]["is_active"] is True


def test_enable_bundle_firewall_options_add_exclude_and_whitelist() -> None:
    server = FakeFirewallServer()
    service = SimpleNamespace(name="MLflow", service_ports={"http": 5000})
    bundle = SimpleNamespace(name="demo", server=server, services=[service])

    result = enable_bundle_firewall_with_options(
        bundle,
        custom_ports=[8080],
        exclude_ports=[5000],
        source_ips=["203.0.113.10", "203.0.113.10", "203.0.113.0/24"],
    )

    assert result.success
    assert server.enabled_ports == [2222, 8080]
    assert server.source_ips_by_port == {
        2222: ["203.0.113.10", "203.0.113.0/24"],
        8080: ["203.0.113.10", "203.0.113.0/24"],
    }


def test_enable_bundle_firewall_options_refuses_ssh_exclusion() -> None:
    server = FakeFirewallServer()
    bundle = SimpleNamespace(name="demo", server=server, services=[])

    result = enable_bundle_firewall_with_options(bundle, exclude_ports=[2222])

    assert not result.success
    assert "without SSH port 2222" in result.message
    assert server.enabled_ports == []


def test_enable_bundle_firewall_options_rejects_invalid_ports() -> None:
    server = FakeFirewallServer()
    bundle = SimpleNamespace(name="demo", server=server, services=[])

    result = enable_bundle_firewall_with_options(bundle, custom_ports=[0])

    assert not result.success
    assert "out of range" in result.message
    assert server.enabled_ports == []


def test_describe_project_firewalls_summarizes_capable_bundles() -> None:
    server = FakeFirewallServer()
    server.status = (
        "Status: active\n"
        "-A MLOX-FIREWALL -p tcp -m tcp --dport 2222 -j ACCEPT"
    )
    bundle = SimpleNamespace(name="demo", server=server, services=[])
    infra = SimpleNamespace(bundles=[bundle])

    result = describe_project_firewalls(infra)

    assert result.success
    assert result.data["summary"] == {"capable": 1, "active": 1, "inactive": 0}
    assert result.data["rows"][0]["open_ports"] == [2222]
