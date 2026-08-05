"""Project-level database service discovery."""

from __future__ import annotations

from typing import Any

from mlox.application.result import OperationResult
from mlox.service import ServiceCapability


def describe_databases(infra) -> OperationResult:
    """List every service advertising the database capability."""

    if infra is None:
        return OperationResult(False, 30, "Infrastructure is unavailable.")

    rows: list[dict[str, Any]] = []
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if not _is_database_service(infra, service):
                continue
            rows.append(
                {
                    "bundle": str(getattr(bundle, "name", "-")),
                    "server": str(getattr(getattr(bundle, "server", None), "ip", "-")),
                    "service": str(getattr(service, "name", "-")),
                    "engine": _service_engine(service),
                    "state": str(getattr(service, "state", "unknown")),
                    "database": _database_name(service),
                    "port": _service_port(service),
                    "endpoint_count": _endpoint_count(service),
                    "endpoints": _service_endpoints(service),
                    "bundle_ref": bundle,
                    "service_ref": service,
                }
            )

    message = "No database services found." if not rows else "Database services loaded."
    return OperationResult(True, 0, message, {"rows": rows})


def _is_database_service(infra, service) -> bool:
    capabilities = {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in (getattr(service, "capabilities", set()) or set())
    }
    if ServiceCapability.DATABASE.value in capabilities:
        return True

    get_config = getattr(infra, "get_service_config", None)
    config = get_config(service) if callable(get_config) else None
    config_capabilities = (
        config.service_capabilities()
        if config and hasattr(config, "service_capabilities")
        else set()
    )
    return ServiceCapability.DATABASE.value in config_capabilities


def _service_endpoints(service) -> str:
    urls = getattr(service, "service_urls", {}) or {}
    values = [str(value) for value in urls.values() if value]
    return ", ".join(dict.fromkeys(values)) or "-"


def _service_engine(service) -> str:
    config_id = str(getattr(service, "service_config_id", "")).strip()
    parts = config_id.split(".")
    if len(parts) > 1 and parts[1]:
        return parts[1]
    class_name = type(service).__name__
    for suffix in ("DockerService", "K3sService", "Service"):
        if class_name.endswith(suffix):
            class_name = class_name[: -len(suffix)]
            break
    return class_name or "-"


def _database_name(service) -> str:
    for attribute in ("db", "database", "database_name"):
        value = getattr(service, attribute, None)
        if value not in (None, ""):
            return str(value)
    return "-"


def _service_port(service) -> str:
    ports = getattr(service, "service_ports", {}) or {}
    values = [str(value) for value in ports.values() if value not in (None, "")]
    if values:
        return ", ".join(dict.fromkeys(values))
    port = getattr(service, "port", None)
    return str(port) if port not in (None, "") else "-"


def _endpoint_count(service) -> int:
    urls = getattr(service, "service_urls", {}) or {}
    return len({str(value) for value in urls.values() if value})
