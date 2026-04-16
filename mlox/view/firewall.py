from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, cast

import pandas as pd
import streamlit as st

from mlox.executors import UbuntuTaskExecutor
from mlox.infra import Bundle, Infrastructure
from mlox.server import ServerCapability


st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
      background: rgba(56, 149, 97, 0.12);
      border: 1px solid rgba(46, 139, 87, 0.6);
      border-radius: 16px;
      padding: 10px;
    }
    div[data-testid="stMetric"] label {color:#cbd5e1}
    div[data-testid="stMetricValue"] {color:#2E8B57}
    div[data-testid="stMetricValue"] * {color:#2E8B57 !important}
    </style>
    """,
    unsafe_allow_html=True,
)


def _is_firewall_up(firewall_status: str | None) -> bool:
    return bool(firewall_status and "Status: active" in firewall_status)


def _collect_firewall_port_rows(bundle: Bundle) -> List[Dict[str, Any]]:
    server = bundle.server
    rows: List[Dict[str, Any]] = [
        {
            "port_number": int(server.port),
            "service": "Server",
            "port_name": "SSH",
        }
    ]
    seen = {(int(server.port), "Server", "SSH")}

    for service in bundle.services:
        service_name = getattr(service, "name", service.__class__.__name__)
        for port_name, port in service.service_ports.items():
            row_key = (int(port), service_name, str(port_name))
            if row_key in seen:
                continue
            seen.add(row_key)
            rows.append(
                {
                    "port_number": int(port),
                    "service": service_name,
                    "port_name": str(port_name),
                }
            )

    return sorted(rows, key=lambda row: (row["port_number"], row["service"]))


def _parse_ports(raw: str) -> List[int]:
    ports: set[int] = set()
    if not raw.strip():
        return []
    for token in raw.replace(" ", "").split(","):
        if not token:
            continue
        if not token.isdigit():
            raise ValueError(f"Invalid port value: {token}")
        port = int(token)
        if port < 1 or port > 65535:
            raise ValueError(f"Port out of range: {port}")
        ports.add(port)
    return sorted(ports)


def _parse_source_whitelist(raw: str) -> Dict[int, Sequence[str] | None]:
    whitelist: Dict[int, Sequence[str] | None] = {}
    if not raw.strip():
        return whitelist

    for lineno, line in enumerate(raw.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        if ":" not in text:
            raise ValueError(
                f"Invalid whitelist line {lineno}: '{line}'. Use '<port>: <ip1>,<ip2>'."
            )
        port_text, ips_text = text.split(":", 1)
        port = int(port_text.strip())
        if port < 1 or port > 65535:
            raise ValueError(f"Port out of range on line {lineno}: {port}")

        ip_values = [ip.strip() for ip in ips_text.split(",") if ip.strip()]
        whitelist[port] = ip_values or None

    return whitelist


def _source_whitelist_to_text(
    source_ips_by_port: Mapping[int, Sequence[str] | None] | None,
) -> str:
    if not source_ips_by_port:
        return ""

    lines: List[str] = []
    for port in sorted(source_ips_by_port):
        ips = source_ips_by_port[port]
        if ips:
            lines.append(f"{port}: {', '.join(ips)}")
    return "\n".join(lines)


def _filter_visible_rows(
    port_rows: List[Dict[str, Any]], open_ports: set[int] | None
) -> List[Dict[str, Any]]:
    if open_ports is None:
        return port_rows

    visible_rows = [row for row in port_rows if row["port_number"] in open_ports]
    known_ports = {row["port_number"] for row in visible_rows}
    visible_rows.extend(
        {
            "port_number": port,
            "service": "Unknown",
            "port_name": "iptables rule",
        }
        for port in sorted(open_ports - known_ports)
    )
    return visible_rows


def _apply_firewall(
    bundle: Bundle,
    action: str,
    ports: Sequence[int],
    source_ips_by_port: Mapping[int, Sequence[str] | None] | None,
) -> None:
    server = bundle.server
    if action == "up":
        server.firewall_up(ports, source_ips_by_port)
    elif action == "update":
        server.firewall_update(ports, source_ips_by_port)
    elif action == "down":
        server.firewall_down()


def firewall() -> None:
    st.title("Firewall")
    st.caption(
        "Manage host-level firewall rules for servers that expose firewall capabilities. "
        "You can enable/disable firewall protection, open/close custom ports, and whitelist source IPs per port."
    )

    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    bundles_with_firewall = [
        bundle
        for bundle in infra.bundles
        if ServerCapability.FIREWALL in getattr(bundle.server, "capabilities", set())
    ]

    if not bundles_with_firewall:
        st.info("No servers with firewall capability detected in this project.")
        return

    rows: List[Dict[str, Any]] = []
    details_by_server: Dict[str, Dict[str, Any]] = {}
    for bundle in bundles_with_firewall:
        server = bundle.server
        firewall_status = server.firewall_status()
        open_ports = UbuntuTaskExecutor._parse_iptables_allowed_ports(firewall_status)
        allowed_rules = UbuntuTaskExecutor._parse_iptables_allowed_rules(firewall_status)
        source_by_port: Dict[int, list[str]] = {}
        if allowed_rules:
            for port, source in allowed_rules:
                if source is None:
                    continue
                source_by_port.setdefault(port, [])
                if source not in source_by_port[port]:
                    source_by_port[port].append(source)

        recommended_rows = _collect_firewall_port_rows(bundle)
        recommended_ports = sorted({row["port_number"] for row in recommended_rows})

        details_by_server[server.uuid] = {
            "bundle": bundle,
            "firewall_status": firewall_status,
            "open_ports": open_ports,
            "recommended_rows": recommended_rows,
            "recommended_ports": recommended_ports,
            "source_by_port": source_by_port,
        }
        rows.append(
            {
                "Name": bundle.name,
                "IP": server.ip,
                "State": server.state,
                "Firewall": "🟢 Active" if _is_firewall_up(firewall_status) else "⚪ Inactive",
                "Open Ports": len(open_ports or []),
                "Recommended": len(recommended_ports),
                "Server UUID": server.uuid,
            }
        )

    active_count = sum(1 for r in rows if r["Firewall"] == "🟢 Active")
    c1, c2, c3 = st.columns(3)
    c1.metric("Firewall-capable Servers", len(rows))
    c2.metric("Firewalls Active", active_count)
    c3.metric("Firewalls Inactive", len(rows) - active_count)

    df = pd.DataFrame(rows)
    selection = st.dataframe(
        df[["Name", "IP", "State", "Firewall", "Open Ports", "Recommended"]],
        hide_index=True,
        use_container_width=True,
        selection_mode="single-row",
        on_select="rerun",
    )

    selected_rows = selection.get("selection", {}).get("rows", [])
    if not selected_rows:
        st.info("Select a server from the table to manage firewall rules.")
        return

    selected_idx = selected_rows[0]
    selected_uuid = rows[selected_idx]["Server UUID"]
    selected_details = details_by_server[selected_uuid]
    bundle = selected_details["bundle"]
    server = bundle.server

    firewall_status = selected_details["firewall_status"]
    open_ports = selected_details["open_ports"]
    recommended_rows = selected_details["recommended_rows"]
    recommended_ports = selected_details["recommended_ports"]
    source_by_port = selected_details["source_by_port"]

    st.divider()
    st.subheader(f"Firewall settings · {bundle.name} ({server.ip})")
    st.code(firewall_status or "Could not fetch firewall status", language="bash")

    visible_rows = _filter_visible_rows(recommended_rows, open_ports)
    st.caption(
        "Known ports include SSH plus service ports. Active iptables rules outside known services are shown as 'Unknown'."
    )
    st.dataframe(
        visible_rows,
        hide_index=True,
        use_container_width=True,
        column_config={
            "port_number": st.column_config.NumberColumn("Port"),
            "service": st.column_config.TextColumn("Service"),
            "port_name": st.column_config.TextColumn("Port Name"),
        },
    )

    ports_key = f"firewall-ports-{server.uuid}"
    whitelist_key = f"firewall-whitelist-{server.uuid}"
    if ports_key not in st.session_state:
        seeded_ports = sorted(set(recommended_ports) | set(open_ports or set()))
        st.session_state[ports_key] = ", ".join(str(port) for port in seeded_ports)
    if whitelist_key not in st.session_state:
        st.session_state[whitelist_key] = _source_whitelist_to_text(source_by_port)

    st.markdown("#### Port Controls")
    st.text_input(
        "Allowed ports (comma-separated)",
        key=ports_key,
        help="Example: 22, 80, 443, 5000",
    )

    quick_port_key = f"firewall-quick-port-{server.uuid}"
    if quick_port_key not in st.session_state:
        st.session_state[quick_port_key] = 8080
    q1, q2, q3 = st.columns([2, 1, 1])
    q1.number_input(
        "Quick custom port",
        key=quick_port_key,
        min_value=1,
        max_value=65535,
        step=1,
    )
    if q2.button("Open Port", type="primary", use_container_width=True):
        ports = _parse_ports(st.session_state[ports_key])
        ports = sorted(set(ports) | {int(st.session_state[quick_port_key])})
        st.session_state[ports_key] = ", ".join(str(port) for port in ports)
        st.rerun()
    if q3.button("Close Port", use_container_width=True):
        ports = _parse_ports(st.session_state[ports_key])
        ports = [p for p in ports if p != int(st.session_state[quick_port_key])]
        st.session_state[ports_key] = ", ".join(str(port) for port in ports)
        st.rerun()

    st.markdown("#### Source IP Whitelist (optional)")
    st.text_area(
        "Per-port whitelist",
        key=whitelist_key,
        help="One line per port. Format: '<port>: <ip-or-cidr>[, <ip-or-cidr>]'. Example: '22: 10.0.0.5/32'.",
        height=120,
    )

    parsed_ports: List[int] = []
    parsed_whitelist: Dict[int, Sequence[str] | None] = {}
    try:
        parsed_ports = _parse_ports(st.session_state[ports_key])
        parsed_whitelist = _parse_source_whitelist(st.session_state[whitelist_key])
    except ValueError as exc:
        st.error(str(exc))

    f_is_up = _is_firewall_up(firewall_status)
    b1, b2, b3 = st.columns(3)
    if b1.button("Enable Firewall", type="primary", disabled=f_is_up):
        _apply_firewall(bundle, "up", parsed_ports, parsed_whitelist or None)
        st.success(f"Firewall enabled for {bundle.name} with ports: {parsed_ports}")
        st.rerun()

    if b2.button("Update Rules", type="primary", disabled=not f_is_up):
        _apply_firewall(bundle, "update", parsed_ports, parsed_whitelist or None)
        st.success(f"Firewall updated for {bundle.name}. Allowed ports: {parsed_ports}")
        st.rerun()

    if b3.button("Disable Firewall", disabled=not f_is_up):
        _apply_firewall(bundle, "down", parsed_ports, parsed_whitelist or None)
        st.success(f"Firewall disabled for {bundle.name}.")
        st.rerun()


firewall()
