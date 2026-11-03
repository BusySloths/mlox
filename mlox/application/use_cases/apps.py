"""Project-wide overview of installed end-user applications."""
from __future__ import annotations

from mlox.application.result import OperationResult
from mlox.application.use_cases.services import get_service_web_ui_address
from mlox.service import ServiceCapability


def describe_apps(infra) -> OperationResult:
    """List app-capable services without contacting remote servers."""
    if infra is None:
        return OperationResult(False, 80, "Infrastructure is unavailable.")

    apps = []
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            capabilities = {str(getattr(item, "value", item)) for item in (getattr(service, "capabilities", set()) or set())}
            if ServiceCapability.APP.value not in capabilities:
                continue
            address = get_service_web_ui_address(service)
            apps.append({
                "id": str(getattr(service, "uuid", "") or ""),
                "name": str(getattr(service, "name", "") or "-"),
                "bundle": str(getattr(bundle, "name", "") or "-"),
                "server": str(getattr(getattr(bundle, "server", None), "ip", "") or "-"),
                "state": str(getattr(service, "state", "unknown") or "unknown"),
                "url": str((address.data or {}).get("url", "")) if address.success else "",
                "service_ref": service,
            })
    return OperationResult(True, 0, "Apps loaded." if apps else "No apps found.", {
        "apps": apps,
        "metrics": {"total": len(apps), "running": sum(row["state"] == "running" for row in apps),
                    "stopped": sum(row["state"] == "stopped" for row in apps),
                    "with_url": sum(bool(row["url"]) for row in apps)},
    })
