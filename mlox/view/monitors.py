from typing import Any, cast

import pandas as pd
import streamlit as st

from mlox.infra import Infrastructure

# Lightweight CSS for badges, chips, and custom tables
st.markdown(
    """
    <style>
    .svc-badge {display:inline-block;padding:2px 8px;border-radius:999px;color:#fff;font-size:12px}
    .svc-chip {display:inline-block;padding:2px 8px;border-radius:999px;background:#111827;color:#e5e7eb;margin-right:6px;margin-bottom:4px;font-size:12px;border:1px solid #374151}
    .svc-table {width:100%;border-collapse:separate;border-spacing:0 6px}
    .svc-table th {text-align:left;padding:8px 10px;color:#94a3b8;font-size:13px}
    .svc-table td {background:#0b1220;padding:10px;border-top:1px solid #1f2937;border-bottom:1px solid #1f2937}
    .svc-pill {display:inline-block;padding:2px 6px;border:1px solid #334155;border-radius:6px;color:#cbd5e1;font-size:12px}
    .link-btn {display:inline-block;padding:6px 10px;background:#0ea5e9;color:#fff;border-radius:6px;text-decoration:none;margin-right:6px;margin-bottom:6px}
    .link-btn:hover {background:#0284c7}
    /* Style Streamlit metric blocks to match highlight color (#2E8B57) */
    div[data-testid="stMetric"] {
      background: rgba(56, 149, 97, 0.12); /* subtle SeaGreen tint */
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


def _collect_monitor_rows(infra: Infrastructure) -> list[dict[str, Any]]:
    monitor_rows: list[dict[str, Any]] = []
    for service in infra.filter_by_group("monitor"):
        bundle = infra.get_bundle_by_service(service)
        if not bundle:
            continue
        monitor_rows.append(
            {
                "ip": bundle.server.ip,
                "server": bundle.name,
                "name": service.name,
                "state": service.state,
                "bundle": bundle,
                "service": service,
            }
        )
    return monitor_rows


def _render_overview(monitor_rows: list[dict[str, Any]]) -> None:
    active_monitors = sum(1 for row in monitor_rows if row["state"] == "running")
    total_servers = {row["server"] for row in monitor_rows}
    col_left, col_middle, col_right = st.columns(3)
    col_left.metric("Monitor Services", len(monitor_rows))
    col_middle.metric("Active", active_monitors)
    col_right.metric("Servers", len(total_servers))
    st.caption("Select a monitor below to view settings or adjust its configuration.")


def manage_monitors() -> None:
    st.title("Monitors")
    st.caption(
        "Track monitoring endpoints deployed across your infrastructure bundles."
    )
    st.divider()

    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except Exception:  # pragma: no cover - defensive path for UI runtime
        st.error("Could not load infrastructure configuration.")
        st.stop()

    monitor_rows = _collect_monitor_rows(infra)
    if not monitor_rows:
        st.info("No monitor services detected yet. Deploy a monitor to get started.")
        return

    _render_overview(monitor_rows)
    st.subheader("Available Monitors")

    table = pd.DataFrame(
        monitor_rows,
        columns=["ip", "server", "name", "state", "bundle", "service"],
    )
    selection = st.dataframe(
        table[["server", "name", "state"]],
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
    )

    selected_rows = selection.get("selection", {}).get("rows", [])
    if not selected_rows:
        st.info("Select a monitor from the table to inspect details.")
        return

    selected_idx = selected_rows[0]
    selected = monitor_rows[selected_idx]
    bundle = selected["bundle"]
    monitor = selected["service"]

    st.divider()
    st.subheader("Selected Monitor")
    col_meta, col_ip = st.columns((2, 1))
    with col_meta:
        st.markdown(f"**Server**: {selected['server']}")
        st.markdown(f"**Service**: {monitor.name}")
        st.markdown(f"**Status**: {monitor.state.title()}")
        service_url = getattr(monitor, "service_url", "")
        if service_url:
            st.markdown(f"**Endpoint**: {service_url}")
    with col_ip:
        st.markdown("**Server IP**")
        st.code(selected["ip"], language="bash")

    config = infra.get_service_config(monitor)
    callable_settings_func = config.instantiate_ui("settings")
    if callable_settings_func and monitor.state == "running":
        st.divider()
        st.subheader("Service Settings")
        callable_settings_func(infra, bundle, monitor)


manage_monitors()
