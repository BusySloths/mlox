"""Provider-neutral firewall policy values.

The policy is deliberately separate from its enforcement: constructing a policy
does not change a host firewall or establish that a source address is trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_network
from typing import Literal

from mlox.firewall_grants import FirewallAccessGrant

@dataclass(frozen=True)
class FirewallStatus:
    """Backend-neutral observation of a server's managed firewall."""

    active: bool | None
    persistence: Literal["enabled", "disabled", "unknown"] = "unknown"
    allowed_ports: tuple[int, ...] = ()
    public_ports: tuple[int, ...] = ()
    trusted_sources: tuple[str, ...] = ()
    error: str = ""
    previous_policy: bool = False
    raw: str = ""
    temporary_grants: tuple[FirewallAccessGrant, ...] | None = None


@dataclass(frozen=True)
class FirewallPolicyRule:
    """A fixed rule to display when reviewing a server's proposed policy."""

    name: str
    description: str
    access: str


def normalize_source(source: str) -> str:
    """Validate and canonicalize an IP address or network, never a hostname."""
    network = ip_network(source.strip(), strict=False)
    if network.prefixlen == 0:
        raise ValueError("A trusted source cannot cover the entire internet.")
    if network.prefixlen == network.max_prefixlen:
        return str(network.network_address)
    return str(network)


@dataclass(frozen=True)
class FirewallPolicy:
    """Public TCP ports and networks trusted to access all inbound ports."""

    public_tcp_ports: tuple[int, ...]
    trusted_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(type(port) is not int or not 1 <= port <= 65535 for port in self.public_tcp_ports):
            raise ValueError("Firewall ports must be integers between 1 and 65535.")
        object.__setattr__(self, "public_tcp_ports", tuple(sorted(set(self.public_tcp_ports))))
        object.__setattr__(
            self, "trusted_sources", tuple(sorted({normalize_source(s) for s in self.trusted_sources}))
        )

    def with_source(self, source: str) -> FirewallPolicy:
        return FirewallPolicy(self.public_tcp_ports, (*self.trusted_sources, source))

    def without_source(self, source: str) -> FirewallPolicy:
        source = normalize_source(source)
        return FirewallPolicy(self.public_tcp_ports, tuple(s for s in self.trusted_sources if s != source))
