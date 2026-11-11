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


def _normalize_ip_values(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ips: list[str] = []
    for value in values:
        ip = str(value).strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        ips.append(ip)
    return ips


def _normalize_whitelist_state(
    source_ips_by_port: Mapping[int, Sequence[str] | None] | None,
) -> Dict[int, list[str]]:
    if not source_ips_by_port:
        return {}
    return {
        int(port): _normalize_ip_values(ips or [])
        for port, ips in source_ips_by_port.items()
        if _normalize_ip_values(ips or [])
    }


def _build_port_table_rows(
    recommended_rows: List[Dict[str, Any]],
    open_ports: Sequence[int],
    whitelist_by_port: Mapping[int, Sequence[str]],
) -> List[Dict[str, Any]]:
    rows_by_port: Dict[int, Dict[str, set[str] | bool]] = {}

    for row in recommended_rows:
        port = int(row["port_number"])
        port_row = rows_by_port.setdefault(
            port,
            {"services": set(), "port_names": set(), "custom": False},
        )
        cast(set[str], port_row["services"]).add(str(row["service"]))
        cast(set[str], port_row["port_names"]).add(str(row["port_name"]))

    known_ports = set(rows_by_port)
    for port in sorted({int(port) for port in open_ports}):
        port_row = rows_by_port.setdefault(
            int(port),
            {"services": set(), "port_names": set(), "custom": True},
        )
        if port not in known_ports:
            port_row["custom"] = True
            cast(set[str], port_row["services"]).add("Custom")
            cast(set[str], port_row["port_names"]).add("Custom Port")

    open_port_set = {int(port) for port in open_ports}
    table_rows: List[Dict[str, Any]] = []
    for port in sorted(rows_by_port):
        if port not in open_port_set:
            continue
        row = rows_by_port[port]
        whitelist = _normalize_ip_values(whitelist_by_port.get(port, []))
        table_rows.append(
            {
                "Port": port,
                "Service": ", ".join(sorted(cast(set[str], row["services"]))),
                "Port Name": ", ".join(sorted(cast(set[str], row["port_names"]))),
                "Whitelisted IPs": whitelist,
            }
        )
    return table_rows


def _source_rules_for_open_ports(
    open_ports: Sequence[int],
    whitelist_by_port: Mapping[int, Sequence[str]],
) -> Dict[int, Sequence[str]]:
    open_port_set = {int(port) for port in open_ports}
    return {
        port: ips
        for port, ips in whitelist_by_port.items()
        if port in open_port_set and _normalize_ip_values(ips)
    }


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
        infra = cast(
            Infrastructure,
            st.session_state.mlox.infrastructure,
        )
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
        allowed_rules = UbuntuTaskExecutor._parse_iptables_allowed_rules(
            firewall_status
        )
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
                "Firewall": "🟢 Active"
                if _is_firewall_up(firewall_status)
                else "⚪ Inactive",
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
        width="stretch",
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
    f_is_up = _is_firewall_up(firewall_status)
    if not f_is_up:
        st.info("This server has no firewall enabled.")
        if st.button("Enable Firewall", type="primary"):
            _apply_firewall(bundle, "up", recommended_ports, None)
            st.success(
                f"Firewall enabled for {bundle.name} with ports: {recommended_ports}"
            )
            st.rerun()
        return

    st.caption(
        "Every port in the table is open. Select ports to remove or whitelist them, "
        "or add a custom port. Changes are applied immediately."
    )

    current_ports = sorted(open_ports or set())
    whitelist_by_port = _normalize_whitelist_state(source_by_port)
    custom_port_input_key = f"firewall-custom-port-input-{server.uuid}"

    if custom_port_input_key not in st.session_state:
        st.session_state[custom_port_input_key] = 8080

    table_rows = _build_port_table_rows(
        recommended_rows,
        current_ports,
        whitelist_by_port,
    )
    port_table = pd.DataFrame(
        table_rows,
        columns=["Port", "Service", "Port Name", "Whitelisted IPs"],
    )
    selection = st.dataframe(
        port_table,
        key=f"firewall-port-table-{server.uuid}",
        hide_index=True,
        width="stretch",
        selection_mode="multi-row",
        on_select="rerun",
        column_order=[
            "Port",
            "Service",
            "Port Name",
            "Whitelisted IPs",
        ],
        column_config={
            "Port": st.column_config.NumberColumn("Port"),
            "Service": st.column_config.TextColumn("Service"),
            "Port Name": st.column_config.TextColumn("Port Name"),
            "Whitelisted IPs": st.column_config.ListColumn(
                "Whitelisted IPs",
                help="Source IPs or CIDRs allowed for this port. Empty means open to any source.",
            ),
        },
    )

    selected_indexes = selection.get("selection", {}).get("rows", [])
    selected_ports = [int(table_rows[index]["Port"]) for index in selected_indexes]

    st.markdown("#### Selected Ports")
    selected_label = (
        f"Selected: {', '.join(str(port) for port in selected_ports)}"
        if selected_ports
        else "No ports selected"
    )
    st.caption(selected_label)

    if st.button(
        "Remove Selected Ports",
        disabled=not selected_ports,
    ):
        selected_port_set = set(selected_ports)
        next_ports = [port for port in current_ports if port not in selected_port_set]
        next_whitelist = _source_rules_for_open_ports(
            next_ports,
            whitelist_by_port,
        )
        _apply_firewall(
            bundle,
            "update",
            next_ports,
            next_whitelist or None,
        )
        st.success(f"Removed ports: {sorted(selected_port_set)}")
        st.rerun()

    current_ip_options = sorted(
        {ip for ips in whitelist_by_port.values() for ip in _normalize_ip_values(ips)}
    )
    selected_ip_defaults = sorted(
        {
            ip
            for port in selected_ports
            for ip in _normalize_ip_values(whitelist_by_port.get(port, []))
        }
    )
    selected_port_token = "-".join(str(port) for port in selected_ports) or "none"
    selected_ips_key = f"firewall-selected-ips-{server.uuid}-{selected_port_token}"
    st.markdown("#### Whitelist Selected Ports")
    w1, w2 = st.columns([3, 1], vertical_alignment="bottom")
    selected_ips = w1.multiselect(
        "Source IPs or CIDRs",
        options=sorted(set(current_ip_options) | set(selected_ip_defaults)),
        default=selected_ip_defaults,
        accept_new_options=True,
        disabled=not selected_ports,
        placeholder="Add IPs or CIDRs",
        help="Applies the same whitelist to every selected port. Empty allows any source.",
        key=selected_ips_key,
    )
    if w2.button(
        "Apply Whitelist",
        disabled=not selected_ports,
        width="stretch",
    ):
        updated_whitelist = dict(whitelist_by_port)
        ips = _normalize_ip_values(selected_ips)
        for port in selected_ports:
            if ips:
                updated_whitelist[port] = ips
            else:
                updated_whitelist.pop(port, None)
        next_whitelist = _source_rules_for_open_ports(
            current_ports,
            updated_whitelist,
        )
        _apply_firewall(
            bundle,
            "update",
            current_ports,
            next_whitelist or None,
        )
        st.success(f"Updated whitelist for ports: {selected_ports}")
        st.rerun()

    st.markdown("#### Add Custom Port")
    c1, c2 = st.columns([1, 1], vertical_alignment="bottom")
    c1.number_input(
        "Port",
        key=custom_port_input_key,
        min_value=1,
        max_value=65535,
        step=1,
    )
    if c2.button("Add Port", type="primary", width="stretch"):
        custom_port = int(st.session_state[custom_port_input_key])
        next_ports = sorted(set(current_ports) | {custom_port})
        next_whitelist = _source_rules_for_open_ports(
            next_ports,
            whitelist_by_port,
        )
        _apply_firewall(
            bundle,
            "update",
            next_ports,
            next_whitelist or None,
        )
        st.success(f"Added port: {custom_port}")
        st.rerun()

    with st.expander("Raw firewall status"):
        st.code(firewall_status or "Could not fetch firewall status", language="bash")

    if st.button("Disable Firewall"):
        _apply_firewall(bundle, "down", current_ports, whitelist_by_port or None)
        st.success(f"Firewall disabled for {bundle.name}.")
        st.rerun()


firewall()
