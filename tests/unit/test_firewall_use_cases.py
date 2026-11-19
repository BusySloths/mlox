from __future__ import annotations

from types import SimpleNamespace

from mlox.application.use_cases.firewall import (
    describe_project_firewalls,
    preview_firewall_policy,
    apply_firewall_draft,
    persist_firewall_draft,
)
from mlox.server import ServerCapability
from mlox.firewall import FirewallPolicy, FirewallPolicyRule, FirewallStatus
from mlox.execution.firewall_policy import validate_ssh_policy


class FakeFirewallServer:
    uuid = "server-1"
    ip = "10.0.0.1"
    port = 2222
    state = "running"
    capabilities = {ServerCapability.FIREWALL}

    def __init__(self) -> None:
        self.enabled_ports: list[int] = []
        self.status = FirewallStatus(active=False)

    def firewall_status(self):
        return self.status

    def firewall_default_policy(self):
        return FirewallPolicy((self.port, 80, 443))

    def firewall_validate_policy(self, policy):
        validate_ssh_policy(policy, self.port)

    def firewall_policy_rules(self):
        return ()


def test_describe_project_firewalls_summarizes_capable_bundles() -> None:
    server = FakeFirewallServer()
    server.status = FirewallStatus(active=True, allowed_ports=(2222,))
    bundle = SimpleNamespace(name="demo", server=server, services=[])
    infra = SimpleNamespace(bundles=[bundle])

    result = describe_project_firewalls(infra)

    assert result.success
    assert result.data["summary"] == {"capable": 1, "active": 1, "inactive": 0, "unknown": 0}
    assert result.data["rows"][0]["open_ports"] == [2222]


def test_status_distinguishes_public_ports_and_trusted_sources():
    server = FakeFirewallServer()
    server.status = FirewallStatus(active=True, persistence="enabled", public_ports=(22,),
                                   trusted_sources=("192.0.2.8",))
    bundle = SimpleNamespace(name="demo", server=server, services=[])
    row = describe_project_firewalls(SimpleNamespace(bundles=[bundle])).data["rows"][0]
    assert row["public_ports"] == [22]
    assert row["trusted_sources"] == ["192.0.2.8"]
    assert row["persistence"] == "enabled"


def test_unavailable_status_is_unknown_not_inactive():
    server = FakeFirewallServer()
    server.status = FirewallStatus(active=None, error="unavailable")
    bundle = SimpleNamespace(name="demo", server=server, services=[])
    result = describe_project_firewalls(SimpleNamespace(bundles=[bundle]))
    assert result.data["summary"]["unknown"] == 1
    assert result.data["summary"]["inactive"] == 0
    assert result.data["rows"][0]["status_error"]


def test_policy_preview_proposes_only_public_literal_peers_without_trusting_them():
    server = FakeFirewallServer()
    bundle = SimpleNamespace(name="target", server=server, services=[])
    def peer(name, address):
        return SimpleNamespace(name=name, server=SimpleNamespace(firewall_peer_address=lambda: address))

    infra = SimpleNamespace(bundles=[
        bundle,
        peer("public", "8.8.8.8"),
        peer("private", None),
        peer("connector", None),
        peer("local", None),
        peer("hostname", None),
    ])
    result = preview_firewall_policy(infra, bundle)
    assert result.success
    assert result.data["public_tcp_ports"] == [80, 443, 2222]
    assert result.data["trusted_sources"] == []
    assert result.data["suggested_project_sources"] == [
        {"bundle": "public", "address": "8.8.8.8", "verified": False}
    ]
    assert "unverified" in result.data["warning"]
    assert server.enabled_ports == []


def test_draft_with_old_ssh_port_is_rejected():
    server = FakeFirewallServer()
    bundle = SimpleNamespace(
        name="demo", server=server, services=[],
        firewall_policy_draft={"public_tcp_ports": [22, 80, 443], "trusted_sources": []},
    )
    result = preview_firewall_policy(SimpleNamespace(bundles=[bundle]), bundle)
    assert not result.success
    assert "SSH port 2222" in result.message


def test_apply_draft_uses_selected_servers_policy():
    server = FakeFirewallServer()
    applied = []
    server.firewall_apply_policy = applied.append
    bundle = SimpleNamespace(name="demo", server=server, services=[],
                             firewall_policy_draft={"public_tcp_ports": [80, 443, 2222],
                                                    "trusted_sources": ["192.0.2.1"]})
    result = apply_firewall_draft(bundle)
    assert result.success and result.data["applied"]
    assert applied[0].trusted_sources == ("192.0.2.1",)
    assert applied[0].public_tcp_ports == (80, 443, 2222)


def test_persist_draft_delegates_policy_and_reports_result():
    server = FakeFirewallServer()
    persisted = []
    server.firewall_persist_policy = persisted.append
    bundle = SimpleNamespace(name="demo", server=server, services=[], firewall_policy_draft=None)
    result = persist_firewall_draft(bundle)
    assert result.success and result.data["persisted"]
    assert persisted[0].public_tcp_ports == (80, 443, 2222)


def test_persist_failure_is_reported():
    server = FakeFirewallServer()
    def fail(policy):
        raise RuntimeError("draft does not match live policy")
    server.firewall_persist_policy = fail
    result = persist_firewall_draft(SimpleNamespace(name="demo", server=server, services=[]))
    assert not result.success
    assert "does not match" in result.message


def test_non_ubuntu_server_controls_policy_and_status_without_backend_metadata():
    class OtherFirewall:
        uuid = "other"
        ip = "example.invalid"
        capabilities = {ServerCapability.FIREWALL}

        def firewall_default_policy(self):
            return FirewallPolicy((8443,))

        def firewall_validate_policy(self, policy):
            if 8443 not in policy.public_tcp_ports:
                raise ValueError("Missing management port")

        def firewall_policy_rules(self):
            return (FirewallPolicyRule("Provider rule", "Custom traffic", "Allow"),)

        def firewall_status(self):
            return FirewallStatus(active=True, persistence="enabled", public_ports=(8443,),
                                  trusted_sources=("2001:db8::1",), raw="provider-specific")

        def firewall_apply_policy(self, policy):
            self.applied = policy

    server = OtherFirewall()
    bundle = SimpleNamespace(name="other", server=server, services=[])
    preview = preview_firewall_policy(SimpleNamespace(bundles=[bundle]), bundle)
    assert preview.success and preview.data["public_tcp_ports"] == [8443]
    assert preview.data["fixed_rules"][0]["name"] == "Provider rule"
    result = apply_firewall_draft(bundle)
    assert result.success and server.applied.public_tcp_ports == (8443,)
    row = result.data["firewall"]
    assert row["public_ports"] == [8443]
    assert row["trusted_sources"] == ["2001:db8::1"]
    assert row["raw_status"] == "provider-specific"
