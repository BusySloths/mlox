from ipaddress import ip_address, ip_network
import os
import subprocess

import pytest

from mlox.firewall import FirewallPolicy
from mlox.execution.firewall_policy import _render_ingress_restore_payload, _render_input_hook_check, render_apply_script, render_persist_script
from mlox.servers.ubuntu.k3s_firewall import compile_k3s_ingress_rules, k3s_ingress_extension


def verdict(rules, *, source, local=True, incoming="eth0", protocol="tcp", port=30000, state="NEW"):
    for rule in rules:
        def value(key):
            return rule[rule.index(key) + 1] if key in rule else None

        if value("-i") and value("-i") != incoming:
            continue
        if "--dst-type" in rule and local:
            continue
        if value("--ctstate") and state not in value("--ctstate").split(","):
            continue
        if value("-s") and ip_address(source) not in ip_network(value("-s")):
            continue
        if value("-p") and value("-p") != protocol:
            continue
        if value("--dport") and int(value("--dport")) != port:
            continue
        return value("-j")
    raise AssertionError("no matching rule")


@pytest.mark.parametrize("family,other,trusted", [(4, "198.51.100.9", "192.0.2.3"), (6, "2001:db8:1::2", "2001:db8:2::3")])
def test_k3s_external_ingress_and_cluster_paths(family, other, trusted):
    policy = FirewallPolicy((22, 80, 443), ("192.0.2.0/24", "2001:db8:2::/64"))
    rules = compile_k3s_ingress_rules(policy, family)
    assert verdict(rules, source=other) == "DROP"
    assert verdict(rules, source=other, protocol="udp") == "DROP"
    assert verdict(rules, source=trusted) == "RETURN"
    assert verdict(rules, source=other, port=443) == "RETURN"
    assert verdict(rules, source=other, state="ESTABLISHED") == "RETURN"
    assert verdict(rules, source=other, incoming="cni0") == "RETURN"
    assert verdict(rules, source=other, incoming="flannel.1") == "RETURN"
    assert verdict(rules, source=other, local=False) == "RETURN"


def test_k3s_ipv6_control_and_invalid_family():
    policy = FirewallPolicy((22,))
    assert verdict(compile_k3s_ingress_rules(policy, 6), source="fe80::1", protocol="ipv6-icmp") == "RETURN"
    with pytest.raises(ValueError):
        compile_k3s_ingress_rules(policy, 5)


def test_k3s_scripts_prepare_and_verify_both_address_families():
    policy = FirewallPolicy((22, 80, 443), ("192.0.2.1", "2001:db8::1"))
    extension = k3s_ingress_extension(policy)
    apply = render_apply_script(policy, 22, docker=False, ingress=extension)
    persist = render_persist_script(policy, 22, docker=False, ingress=extension)
    for script in (apply, persist):
        subprocess.run(["sh", "-n"], input=script, text=True, check=True)
    assert "*mangle" in apply
    assert "-I PREROUTING 1 -j MLOX-INGRESS" in apply
    assert "-A MLOX-POLICY-IN -i cni0 -j ACCEPT" in apply
    assert "iptables-restore --test --noflush" in apply
    assert "ip6tables-restore --test --noflush" in apply
    assert "iptables -t mangle -C MLOX-INGRESS" in persist
    assert "ip6tables -t mangle -C MLOX-INGRESS" in persist


def test_restore_payload_uses_iptables_negation_syntax():
    policy = FirewallPolicy((22, 443))
    for family in (4, 6):
        payload = _render_ingress_restore_payload(compile_k3s_ingress_rules(policy, family))
        assert "-m addrtype ! --dst-type LOCAL -j RETURN\n" in payload
        assert "'!'" not in payload


def test_restore_payload_rejects_unsafe_tokens():
    with pytest.raises(ValueError, match="Unsupported character"):
        _render_ingress_restore_payload((("-s", "bad\nCOMMIT", "-j", "RETURN"),))


@pytest.mark.parametrize("family", ["iptables", "ip6tables"])
@pytest.mark.parametrize("preceding,expected", [
    ("", 0),
    ('-A INPUT -m comment --comment "kube-router netpol - 4IA2OSFRMVNDXBVV" -j KUBE-ROUTER-INPUT\n', 0),
    ("-A INPUT -j ACCEPT\n", 1),
    ('-A INPUT -m comment --comment "kube-router netpol - BAD" -j ACCEPT\n', 1),
])
def test_k3s_persistence_accepts_only_known_input_predecessor(tmp_path, family, preceding, expected):
    tool = tmp_path / family
    tool.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_RULES"\n')
    tool.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
           "TEST_RULES": preceding + "-A INPUT -j MLOX-POLICY-IN"}
    command = _render_input_hook_check(family, ingress=True)
    result = subprocess.run(["sh", "-eu", "-c", command], env=env, capture_output=True)
    assert result.returncode == expected
