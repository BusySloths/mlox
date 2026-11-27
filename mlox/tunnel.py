"""Transport-neutral values for service tunnel plans and local bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TunnelEndpoint:
    """One TCP endpoint reachable through the server hosting a service."""

    service_uuid: str
    name: str
    server_uuid: str
    remote_host: str
    remote_port: int
    protocol: Literal["https", "postgres", "tcp"] = "tcp"
    tls_server_name: str | None = None

    def __post_init__(self) -> None:
        if not all((self.service_uuid, self.name, self.server_uuid, self.remote_host)):
            raise ValueError("Tunnel endpoints require a service, name, server and remote host.")
        if type(self.remote_port) is not int or not 1 <= self.remote_port <= 65535:
            raise ValueError("Tunnel endpoint port must be between 1 and 65535.")
        if self.protocol not in ("https", "postgres", "tcp"):
            raise ValueError("Unsupported tunnel endpoint protocol.")


@dataclass(frozen=True)
class TunnelBinding:
    """Actual loopback address assigned to an endpoint in a running group."""

    endpoint: TunnelEndpoint
    local_port: int
    local_host: Literal["127.0.0.1"] = "127.0.0.1"

    def __post_init__(self) -> None:
        if self.local_host != "127.0.0.1":
            raise ValueError("Tunnel listeners must bind to IPv4 loopback.")
        if type(self.local_port) is not int or not 1 <= self.local_port <= 65535:
            raise ValueError("Local tunnel port must be between 1 and 65535.")


@dataclass(frozen=True)
class TunnelPlan:
    """A service's tunnel requirements; no network changes are made here."""

    service_uuid: str
    endpoints: tuple[TunnelEndpoint, ...]

    def __post_init__(self) -> None:
        if not self.service_uuid or not self.endpoints:
            raise ValueError("A tunnel plan requires a service and at least one endpoint.")
        keys = [(endpoint.service_uuid, endpoint.name) for endpoint in self.endpoints]
        if len(keys) != len(set(keys)):
            raise ValueError("Tunnel endpoint names must be unique per service.")


def direct_endpoint(infra, service, name: str, port: int, protocol: Literal["https", "postgres", "tcp"]) -> TunnelEndpoint:
    """Describe a service port on its hosting server without network I/O."""
    bundle = infra.get_bundle_by_service(service)
    if bundle is None or bundle.server is None:
        raise ValueError("Tunnel service is not associated with a server.")
    server = bundle.server
    return TunnelEndpoint(str(service.uuid), name, str(server.uuid), "127.0.0.1", int(port), protocol, str(server.ip))


def find_binding(bindings: tuple[TunnelBinding, ...], service_uuid: str, name: str) -> TunnelBinding:
    matches = [binding for binding in bindings if binding.endpoint.service_uuid == str(service_uuid) and binding.endpoint.name == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one tunnel binding for endpoint {name!r}.")
    return matches[0]
