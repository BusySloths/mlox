from __future__ import annotations

from typing import Any, Mapping, Sequence

from mlox.application.result import OperationResult
from mlox.executors import UbuntuTaskExecutor
from mlox.server import ServerCapability


def describe_project_firewalls(infra) -> OperationResult:
    """Return firewall status for every firewall-capable bundle."""

    bundles = _firewall_bundles(infra)
    rows = []
    active_count = 0
    for bundle in bundles:
        detail = _describe_bundle(bundle)
        rows.append(detail)
        if detail["is_active"]:
            active_count += 1

    return OperationResult(
        True,
        0,
        "Firewall status loaded.",
        {
            "rows": rows,
            "summary": {
                "capable": len(rows),
                "active": active_count,
                "inactive": len(rows) - active_count,
            },
        },
    )


def describe_bundle_firewall(bundle) -> OperationResult:
    return OperationResult(
        True,
        0,
        f"Firewall status loaded for {getattr(bundle, 'name', '-')}.",
        {"firewall": _describe_bundle(bundle)},
    )


def enable_bundle_firewall(bundle) -> OperationResult:
    ports = collect_firewall_ports(bundle)
    try:
        bundle.server.firewall_up(ports)
    except Exception as exc:
        return OperationResult(
            False,
            1,
            f"Could not enable firewall for {getattr(bundle, 'name', '-')}: {exc}",
        )
    return describe_bundle_firewall(bundle)


def enable_bundle_firewall_with_options(
    bundle,
    *,
    custom_ports: Sequence[int] | None = None,
    exclude_ports: Sequence[int] | None = None,
    source_ips: Sequence[str] | None = None,
) -> OperationResult:
    recommended_ports = set(collect_firewall_ports(bundle))
    ssh_port = _server_port(getattr(bundle, "server", None))
    custom_result = _normalize_ports(custom_ports or [])
    if not custom_result.success:
        return custom_result
    exclude_result = _normalize_ports(exclude_ports or [])
    if not exclude_result.success:
        return exclude_result

    custom = set(custom_result.data["ports"])
    excluded = set(exclude_result.data["ports"])
    if ssh_port in excluded:
        return OperationResult(
            False,
            4,
            f"Refusing to enable firewall without SSH port {ssh_port}.",
        )

    ports = sorted((recommended_ports | custom) - excluded)
    normalized_sources = _normalize_source_ips(source_ips or [])
    source_ips_by_port = (
        {port: normalized_sources for port in ports} if normalized_sources else None
    )
    try:
        bundle.server.firewall_up(ports, source_ips_by_port)
    except Exception as exc:
        return OperationResult(
            False,
            5,
            f"Could not enable firewall for {getattr(bundle, 'name', '-')}: {exc}",
        )
    return describe_bundle_firewall(bundle)


def disable_bundle_firewall(bundle) -> OperationResult:
    try:
        bundle.server.firewall_down()
    except Exception as exc:
        return OperationResult(
            False,
            2,
            f"Could not disable firewall for {getattr(bundle, 'name', '-')}: {exc}",
        )
    return describe_bundle_firewall(bundle)


def update_bundle_firewall(
    bundle,
    ports: Sequence[int] | Mapping[int, Sequence[str] | None],
    source_ips_by_port: Mapping[int, Sequence[str] | None] | None = None,
) -> OperationResult:
    try:
        bundle.server.firewall_update(ports, source_ips_by_port)
    except Exception as exc:
        return OperationResult(
            False,
            3,
            f"Could not update firewall for {getattr(bundle, 'name', '-')}: {exc}",
        )
    return describe_bundle_firewall(bundle)


def collect_firewall_port_rows(bundle) -> list[dict[str, Any]]:
    server = getattr(bundle, "server", None)
    rows = []
    seen: set[tuple[int, str, str]] = set()

    ssh_port = _server_port(server)
    _add_port_row(rows, seen, ssh_port, "Server", "SSH")

    for service in getattr(bundle, "services", []) or []:
        service_name = str(getattr(service, "name", service.__class__.__name__))
        for port_name, port in (getattr(service, "service_ports", {}) or {}).items():
            _add_port_row(rows, seen, port, service_name, str(port_name))

    return sorted(rows, key=lambda row: (row["port"], row["service"], row["name"]))


def collect_firewall_ports(bundle) -> list[int]:
    return sorted({int(row["port"]) for row in collect_firewall_port_rows(bundle)})


def firewall_summary_for_bundle(bundle) -> dict[str, Any]:
    server = getattr(bundle, "server", None)
    capable = _has_firewall_capability(server)
    rows = collect_firewall_port_rows(bundle) if capable else []
    return {
        "capable": capable,
        "recommended_ports": [row["port"] for row in rows],
        "recommended_rows": rows,
    }


def _firewall_bundles(infra) -> list:
    return [
        bundle
        for bundle in getattr(infra, "bundles", []) or []
        if _has_firewall_capability(getattr(bundle, "server", None))
    ]


def _describe_bundle(bundle) -> dict[str, Any]:
    server = getattr(bundle, "server", None)
    recommended_rows = collect_firewall_port_rows(bundle)
    recommended_ports = sorted({int(row["port"]) for row in recommended_rows})
    status = None
    error = ""
    try:
        status = server.firewall_status()
    except Exception as exc:
        error = str(exc)

    open_ports = UbuntuTaskExecutor._parse_iptables_allowed_ports(status)
    allowed_rules = UbuntuTaskExecutor._parse_iptables_allowed_rules(status)
    source_by_port = _source_ips_by_port(allowed_rules)
    is_active = _is_firewall_up(status)

    return {
        "id": str(getattr(server, "uuid", getattr(bundle, "name", ""))),
        "bundle": getattr(bundle, "name", "-"),
        "server": str(getattr(server, "ip", "-")),
        "server_state": str(getattr(server, "state", "unknown")),
        "is_active": is_active,
        "status": "Active" if is_active else "Inactive",
        "status_error": error,
        "open_ports": sorted(open_ports or []),
        "open_ports_unknown": open_ports is None,
        "recommended_ports": recommended_ports,
        "recommended_rows": recommended_rows,
        "source_by_port": source_by_port,
        "raw_status": status or "",
        "bundle_ref": bundle,
    }


def _source_ips_by_port(
    allowed_rules: set[tuple[int, str | None]] | None,
) -> dict[int, list[str]]:
    source_by_port: dict[int, list[str]] = {}
    for port, source in allowed_rules or set():
        if source is None:
            continue
        source_by_port.setdefault(int(port), [])
        if source not in source_by_port[int(port)]:
            source_by_port[int(port)].append(source)
    return source_by_port


def _normalize_source_ips(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        source = str(value).strip()
        if source and source not in seen:
            seen.add(source)
            normalized.append(source)
    return normalized


def _normalize_ports(values: Sequence[int]) -> OperationResult:
    ports: set[int] = set()
    try:
        for value in values:
            port = int(value)
            if port < 1 or port > 65535:
                return OperationResult(
                    False,
                    6,
                    f"Firewall port out of range: {port}.",
                )
            ports.add(port)
    except (TypeError, ValueError) as exc:
        return OperationResult(False, 7, f"Invalid firewall port: {exc}.")
    return OperationResult(True, 0, "Firewall ports normalized.", {"ports": sorted(ports)})


def _add_port_row(
    rows: list[dict[str, Any]],
    seen: set[tuple[int, str, str]],
    port: object,
    service: str,
    name: str,
) -> None:
    try:
        port_number = int(port)
    except (TypeError, ValueError):
        return
    key = (port_number, service, name)
    if key in seen:
        return
    seen.add(key)
    rows.append({"port": port_number, "service": service, "name": name})


def _server_port(server) -> int:
    try:
        return int(getattr(server, "port", 22) or 22)
    except (TypeError, ValueError):
        return 22


def _has_firewall_capability(server) -> bool:
    capabilities = getattr(server, "capabilities", set()) or set()
    return ServerCapability.FIREWALL in capabilities or "firewall" in capabilities


def _is_firewall_up(firewall_status: str | None) -> bool:
    return bool(firewall_status and "Status: active" in firewall_status)
