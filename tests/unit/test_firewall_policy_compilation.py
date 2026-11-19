"""Check the intended policy independently of live firewall tools."""

from ipaddress import ip_address, ip_network

import pytest

from mlox.execution.firewall_policy import compile_firewall_rules, prepare_firewall_rules, render_unattached_chains
from mlox.firewall import FirewallPolicy


def evaluate(rules, *, source, protocol="tcp", port=0, incoming="eth0", outgoing="docker0", state="NEW"):
    for rule in rules:
        args = list(rule)
        def value(option):
            return args[args.index(option) + 1] if option in args else None
        def interface_matches(pattern, actual):
            return actual.startswith(pattern[:-1]) if pattern.endswith("+") else pattern == actual
        if value("-i") and not interface_matches(value("-i"), incoming):
            continue
        if value("-o") and not interface_matches(value("-o"), outgoing):
            continue
        if value("-s") and ip_address(source) not in ip_network(value("-s")):
            continue
        if value("-p") and value("-p") != protocol:
            continue
        if value("--ctstate") and state not in value("--ctstate").split(","):
            continue
        destination = value("--dport") or value("--ctorigdstport")
        if destination and int(destination) != port:
            continue
        return value("-j")
    return None


@pytest.mark.parametrize("family,public,trusted", [(4, "198.51.100.9", "192.0.2.4"), (6, "2001:db8:1::9", "2001:db8:2::4")])
def test_host_and_docker_enforce_default_and_trusted_access(family, public, trusted):
    policy = FirewallPolicy((2222, 80, 443), ("192.0.2.0/24", "2001:db8:2::/64"))
    rules = compile_firewall_rules(policy, family)
    for port in (80, 443, 2222):
        assert evaluate(rules.input_rules, source=public, port=port) == "ACCEPT"
        assert evaluate(rules.docker_rules, source=public, port=port) == "RETURN"
    for protocol in ("tcp", "udp"):
        assert evaluate(rules.input_rules, source=public, protocol=protocol, port=5432) == "DROP"
        assert evaluate(rules.docker_rules, source=public, protocol=protocol, port=5432) == "DROP"
        assert evaluate(rules.input_rules, source=trusted, protocol=protocol, port=5432) == "ACCEPT"
        assert evaluate(rules.docker_rules, source=trusted, protocol=protocol, port=5432) == "RETURN"
    assert evaluate(rules.docker_rules, source=public, port=5432, outgoing="eth1") == "RETURN"
    assert evaluate(rules.input_rules, source=public, port=5432, state="ESTABLISHED") == "ACCEPT"


@pytest.mark.parametrize("family,source", [(4, "172.19.0.2"), (6, "fd00::2")])
def test_proxy_can_reach_host_published_ports_without_opening_them_externally(family, source):
    rules = compile_firewall_rules(FirewallPolicy((22, 80, 443)), family)
    for bridge in ("docker0", "br-0123456789ab"):
        assert evaluate(rules.input_rules, source=source, port=1099, incoming=bridge) == "ACCEPT"
        assert evaluate(rules.input_rules, source=source, port=9001, incoming=bridge) == "ACCEPT"
    assert evaluate(rules.input_rules, source=source, port=1099, incoming="eth0") == "DROP"
    assert evaluate(rules.input_rules, source=source, port=9001, incoming="br0") == "DROP"


def test_ipv6_icmp_remains_available_for_network_operation():
    rules = compile_firewall_rules(FirewallPolicy((22, 80, 443)), 6)
    assert evaluate(rules.input_rules, source="fe80::1", protocol="ipv6-icmp") == "ACCEPT"


def test_invalid_address_family_is_rejected():
    with pytest.raises(ValueError):
        compile_firewall_rules(FirewallPolicy((22, 80, 443)), 5)


def test_preparation_requires_configured_ssh_before_compiling_either_family():
    with pytest.raises(ValueError, match="SSH port 2222"):
        prepare_firewall_rules(FirewallPolicy((22, 80, 443)), 2222)
    v4, v6 = prepare_firewall_rules(FirewallPolicy((2222, 80, 443)), 2222)
    assert (v4.family, v6.family) == (4, 6)


def test_restore_input_builds_policy_chains_without_attaching_them():
    rules, _ = prepare_firewall_rules(FirewallPolicy((2222, 80, 443), ("192.0.2.10",)), 2222)
    payload = render_unattached_chains(rules)
    assert payload.startswith("*filter\n:MLOX-POLICY-IN - [0:0]\n")
    assert "-A MLOX-POLICY-IN -p tcp --dport 2222 -j ACCEPT\n" in payload
    assert "-A MLOX-POLICY-DOCKER -o docker0 -s 192.0.2.10 -j RETURN\n" in payload
    assert "-A INPUT " not in payload
    assert "-A DOCKER-USER " not in payload
    assert payload.endswith("COMMIT\n")
