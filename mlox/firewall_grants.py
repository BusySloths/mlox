"""Values and reconciliation helpers for temporary firewall access grants.

Grant records are distinct from the persistent firewall policy. An address can
be shared by multiple operators, so its access is retained until the last
active grant for that address expires or is removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address


@dataclass(frozen=True)
class FirewallAccessGrant:
    grant_id: str
    address: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.grant_id:
            raise ValueError("A firewall grant requires an identifier.")
        address = ip_address(self.address)
        if address.is_unspecified or address.is_loopback or address.is_multicast:
            raise ValueError("A firewall grant requires a unicast client address.")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("A firewall grant expiration must include a timezone.")
        object.__setattr__(self, "address", str(address))


def active_source_expirations(grants: list[FirewallAccessGrant], *, now: datetime) -> dict[str, datetime]:
    """Return the latest expiry per address without extending another grant."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The current time must include a timezone.")
    result: dict[str, datetime] = {}
    for grant in grants:
        if grant.expires_at > now:
            previous = result.get(grant.address)
            if previous is None or grant.expires_at > previous:
                result[grant.address] = grant.expires_at
    return result


def ssh_client_address(connection_info: str) -> str:
    """Extract the client IP from a server-observed SSH_CONNECTION value."""
    fields = connection_info.split()
    if len(fields) != 4:
        raise ValueError("SSH did not provide a complete connection address.")
    client, client_port, server, server_port = fields
    address = ip_address(client)
    ip_address(server)
    if any(not port.isdecimal() or not 1 <= int(port) <= 65535 for port in (client_port, server_port)):
        raise ValueError("SSH connection contains an invalid port.")
    if address.is_unspecified or address.is_loopback or address.is_multicast:
        raise ValueError("SSH connection does not identify a usable client address.")
    return str(address)
