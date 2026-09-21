"""Typed dictionary contracts for public application operation payloads.

The runtime representation deliberately remains ``dict`` so existing CLI, TUI,
and SDK callers keep working. Payloads containing live domain references are
marked as such; future external adapters must serialize those references rather
than returning them directly.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from mlox.infra import Bundle
from mlox.server import AbstractServer
from mlox.service import AbstractService


class ConfigSummary(TypedDict):
    """Serializable identity of an available server or service configuration."""

    id: str
    path: str


class ListConfigsData(TypedDict):
    """Payload returned when listing configuration templates."""

    configs: list[ConfigSummary]


class ServerSummary(TypedDict):
    """Serializable server row returned by ``list_servers``."""

    ip: str
    state: str
    service_count: int
    service_config_id: str | None
    port: str | int | None
    discovered: str | None
    backend: list[str]


class ListServersData(TypedDict):
    """Payload returned when listing project servers."""

    servers: list[ServerSummary]


class BundleData(TypedDict):
    """Internal payload carrying a live bundle reference."""

    bundle: Bundle


class ServerOperationData(BundleData):
    """Internal payload carrying live bundle and server references."""

    server: AbstractServer
    backend_status: NotRequired[dict[str, Any]]


class ServerHealthData(TypedDict):
    """Internal server-health payload with a live server reference."""

    server: AbstractServer
    health: dict[str, Any]


class ServiceSummary(TypedDict):
    """Serializable service row returned by ``list_services``."""

    name: str
    service_config_id: str
    server_ip: str
    state: str
    labels: list[str]
    ports: list[str]
    urls: list[str]


class ListServicesData(TypedDict):
    """Payload returned when listing project services."""

    services: list[ServiceSummary]


class ServiceData(TypedDict):
    """Internal payload carrying a live service reference."""

    service: AbstractService


class ServiceHealthData(ServiceData):
    """Internal service-health payload with a live service reference."""

    health: dict[str, Any]


class ServiceLogsData(TypedDict):
    """Payload returned when reading recent service logs."""

    logs: str


class ListModelsData(TypedDict):
    """Payload returned when listing models from registry services.

    Model registries currently return provider-defined fields, so each record is
    intentionally open until the model API is normalized.
    """

    models: list[dict[str, Any]]


class ModelExampleData(TypedDict):
    """Payload containing a generated model invocation example."""

    example: str
