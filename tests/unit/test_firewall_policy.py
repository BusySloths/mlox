import pytest

from mlox.firewall import FirewallPolicy
from mlox.contracts.servers.operations import AbstractFirewallServer


def test_policy_normalizes_public_ports():
    policy = FirewallPolicy((2222, 80, 443))
    assert policy.public_tcp_ports == (80, 443, 2222)
    assert policy.trusted_sources == ()


def test_incomplete_firewall_contract_cannot_be_instantiated():
    class Incomplete(AbstractFirewallServer):
        def firewall_down(self):
            pass

        def firewall_status(self):
            pass

    with pytest.raises(TypeError):
        Incomplete()


def test_trusted_sources_are_canonical_and_managed_independently():
    policy = FirewallPolicy((22, 80, 443)).with_source("192.0.2.1/24")
    policy = policy.with_source("2001:db8::1/128").with_source("192.0.2.0/24")
    assert policy.trusted_sources == ("192.0.2.0/24", "2001:db8::1")
    assert policy.without_source("192.0.2.44/24").trusted_sources == ("2001:db8::1",)
    assert len(policy.trusted_sources) == 2


@pytest.mark.parametrize("source", ["example.com", "0.0.0.0/0", "::/0", "", "1.2.3.999"])
def test_unbounded_or_invalid_sources_are_rejected(source):
    with pytest.raises(ValueError):
        FirewallPolicy((22, 80, 443)).with_source(source)


@pytest.mark.parametrize("port", [0, 65536, True, "22"])
def test_invalid_public_ports_are_rejected(port):
    with pytest.raises(ValueError):
        FirewallPolicy((port, 80, 443))
