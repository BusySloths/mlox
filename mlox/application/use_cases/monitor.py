from __future__ import annotations

from typing import Any

from mlox.application.result import OperationResult
from mlox.service import ServiceCapability


def describe_monitoring(infra) -> OperationResult:
    """Collect compact project-level resource metrics from monitor services."""

    if infra is None:
        return OperationResult(False, 30, "Infrastructure is unavailable.")

    rows: list[dict[str, Any]] = []
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            if not _is_monitor_service(infra, service):
                continue
            row = _monitor_row(bundle, service)
            rows.append(row)

    message = "No monitor services found." if not rows else "Monitor metrics loaded."
    return OperationResult(True, 0, message, {"rows": rows})


def _monitor_row(bundle, service) -> dict[str, Any]:
    base = {
        "bundle": str(getattr(bundle, "name", "-")),
        "server": str(getattr(getattr(bundle, "server", None), "ip", "-")),
        "service": str(getattr(service, "name", "-")),
        "bundle_ref": bundle,
        "service_ref": service,
        "state": str(getattr(service, "state", "unknown")),
        "cpu_used_ratio": None,
        "ram_free_ratio": None,
        "disk_free_ratio": None,
        "network_in_rate": None,
        "network_out_rate": None,
        "network_unit": None,
        "latest_timestamp": None,
        "metric_points": 0,
        "message": "",
    }
    get_snapshot = getattr(service, "get_monitor_snapshot", None)
    if not callable(get_snapshot):
        base["message"] = "Monitor snapshot is not supported by this service."
        return base

    try:
        snapshot = get_snapshot(bundle) or {}
    except Exception as exc:  # pragma: no cover - remote IO defensive path
        base["message"] = f"Failed to load monitor metrics: {exc}"
        return base

    base.update(
        {
            key: snapshot.get(key)
            for key in (
                "cpu_used_ratio",
                "ram_free_ratio",
                "disk_free_ratio",
                "network_in_rate",
                "network_out_rate",
                "network_unit",
                "latest_timestamp",
                "metric_points",
            )
            if key in snapshot
        }
    )
    messages = snapshot.get("messages") or []
    base["message"] = " ".join(str(message) for message in messages if message)
    return base


def _is_monitor_service(infra, service) -> bool:
    capabilities = {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in (getattr(service, "capabilities", set()) or set())
    }
    if ServiceCapability.MONITOR.value in capabilities or "monitor" in capabilities:
        return True

    get_config = getattr(infra, "get_service_config", None)
    config = get_config(service) if callable(get_config) else None
    service_capabilities = (
        config.service_capabilities() if config and hasattr(config, "service_capabilities") else set()
    )
    return ServiceCapability.MONITOR.value in service_capabilities
