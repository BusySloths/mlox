"""K3s host ingress policy for packets before Kubernetes destination NAT.

These rules are compiled separately from installation so they can be reviewed
and tested without changing a host. RETURN delegates permitted traffic back to
the existing network stack; it does not override Kubernetes or other firewalls.
"""

from __future__ import annotations

from ipaddress import ip_network
from typing import Literal

from mlox.firewall import FirewallPolicy
from mlox.execution.firewall_policy import FirewallIngressExtension


def compile_k3s_ingress_rules(
    policy: FirewallPolicy, family: Literal[4, 6]
) -> tuple[tuple[str, ...], ...]:
    """Build pre-DNAT rules for traffic addressed to a node's local IP.

    The standard K3s CNI bridge and Flannel interface are internal paths. They
    must be exempted based on the incoming interface, not a spoofable source
    CIDR. Other CNI configurations require their own implementation.
    """
    if family not in (4, 6):
        raise ValueError("Address family must be 4 or 6.")
    rules: list[tuple[str, ...]] = [
        ("-i", "lo", "-j", "RETURN"),
        ("-i", "cni0", "-j", "RETURN"),
        ("-i", "flannel.1", "-j", "RETURN"),
        ("-m", "addrtype", "!", "--dst-type", "LOCAL", "-j", "RETURN"),
        ("-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"),
    ]
    if family == 6:
        rules.append(("-p", "ipv6-icmp", "-j", "RETURN"))
    for source in policy.trusted_sources:
        if ip_network(source).version == family:
            rules.append(("-s", source, "-j", "RETURN"))
    for port in policy.public_tcp_ports:
        rules.append(("-p", "tcp", "--dport", str(port), "-j", "RETURN"))
    rules.append(("-j", "DROP"))
    return tuple(rules)


def k3s_ingress_extension(policy: FirewallPolicy) -> FirewallIngressExtension:
    return FirewallIngressExtension(
        input_interfaces=("cni0", "flannel.1"),
        ipv4_rules=compile_k3s_ingress_rules(policy, 4),
        ipv6_rules=compile_k3s_ingress_rules(policy, 6),
    )
