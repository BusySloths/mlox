"""Project-wide overview of apps and the proxies that relay them."""
from __future__ import annotations

from urllib.parse import urlsplit
import webbrowser

from mlox.application.result import OperationResult
from mlox.application.use_cases.services import get_service_web_ui_address
from mlox.service import AbstractProxyService, ServiceCapability


UNPROXIED_APPS = "__unproxied__"


def open_app(row, *, opener=None) -> OperationResult:
    """Open the selected proxy URL, or the app's direct web UI URL."""
    urls = row.get("proxy_urls") or []
    url = str(urls[0] if urls else row.get("url") or "")
    if not url:
        return OperationResult(False, 24, "App web UI address is not available yet. Set up the service first.")
    try:
        if (opener or webbrowser.open)(url) is False:
            return OperationResult(False, 25, "Failed to open app web UI.")
    except Exception as exc:
        return OperationResult(False, 25, f"Failed to open app web UI: {exc}")
    return OperationResult(True, 0, f"Opened app web UI: {url}", {"url": url})


def _capabilities(service):
    return {str(getattr(item, "value", item)) for item in (getattr(service, "capabilities", set()) or set())}


def _legacy_route_matches(route, proxy_bundle, app_rows):
    """Infer old local routes only where one app has the exact backend port."""
    try:
        target = urlsplit(str(route.get("backend", "")))
        port = target.port
    except ValueError:
        return []
    host = str(target.hostname or "").lower()
    server_ip = str(getattr(getattr(proxy_bundle, "server", None), "ip", "") or "").lower()
    if not port or host not in {"host.docker.internal", server_ip}:
        return []
    matches = []
    for row in app_rows:
        if row["bundle_ref"] is not proxy_bundle:
            continue
        values = (getattr(row["service_ref"], "service_ports", {}) or {}).values()
        ports = {int(value) for value in values if str(value).isdigit()}
        try:
            address = urlsplit(row["url"])
            if address.port:
                ports.add(address.port)
        except ValueError:
            pass
        if port in ports:
            matches.append(row)
    return matches if len(matches) == 1 else []


def describe_apps(infra) -> OperationResult:
    """List apps and proxy relationships using persisted project state."""
    if infra is None:
        return OperationResult(False, 80, "Infrastructure is unavailable.")

    apps = []
    proxies = []
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            capabilities = _capabilities(service)
            if ServiceCapability.APP.value in capabilities:
                address = get_service_web_ui_address(service)
                apps.append({
                    "id": str(getattr(service, "uuid", "") or ""),
                    "name": str(getattr(service, "name", "") or "-"),
                    "bundle": str(getattr(bundle, "name", "") or "-"),
                    "server": str(getattr(getattr(bundle, "server", None), "ip", "") or "-"),
                    "state": str(getattr(service, "state", "unknown") or "unknown"),
                    "url": str((address.data or {}).get("url", "")) if address.success else "",
                    "service_ref": service, "bundle_ref": bundle,
                })
            if ServiceCapability.PROXY.value in capabilities and isinstance(service, AbstractProxyService):
                proxies.append({"id": str(service.uuid), "name": str(service.name),
                                "bundle": str(getattr(bundle, "name", "") or "-"),
                                "state": str(getattr(service, "state", "unknown")),
                                "service_ref": service, "bundle_ref": bundle})

    groups = {UNPROXIED_APPS: []}
    linked = set()
    for proxy in proxies:
        proxy_id = proxy["id"]
        groups[proxy_id] = []
        seen = set()
        for hostname, route in proxy["service_ref"].list_routes().items():
            service_id = str(route.get("service_uuid") or "")
            if service_id:
                matches = [row for row in apps if row["id"] == service_id]
            else:
                matches = _legacy_route_matches(route, proxy["bundle_ref"], apps)
            for row in matches:
                marker = id(row["service_ref"])
                linked.add(marker)
                if marker not in seen:
                    groups[proxy_id].append({**row, "proxy_urls": [f"https://{hostname}"]})
                    seen.add(marker)
                else:
                    next(item for item in groups[proxy_id] if item["service_ref"] is row["service_ref"])["proxy_urls"].append(f"https://{hostname}")
        proxy["app_count"] = len(groups[proxy_id])
    groups[UNPROXIED_APPS] = [row for row in apps if id(row["service_ref"]) not in linked]
    proxies.insert(0, {"id": UNPROXIED_APPS, "name": "No proxy", "bundle": "—", "state": "—", "app_count": len(groups[UNPROXIED_APPS])})
    return OperationResult(True, 0, "Apps loaded." if apps else "No apps found.", {
        "apps": apps, "proxies": proxies, "apps_by_proxy": groups,
        "metrics": {"total": len(apps), "running": sum(row["state"] == "running" for row in apps),
                    "stopped": sum(row["state"] == "stopped" for row in apps),
                    "with_url": sum(bool(row["url"]) for row in apps)},
    })
