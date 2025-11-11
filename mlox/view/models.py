import pandas as pd
import streamlit as st

from typing import Any, Dict, List, Optional, cast

from mlox.infra import Infrastructure


st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
      background: rgba(15, 118, 110, 0.12);
      border: 1px solid rgba(15, 118, 110, 0.5);
      border-radius: 16px;
      padding: 12px;
    }
    div[data-testid="stMetric"] label {color:#cbd5e1}
    div[data-testid="stMetricValue"] {color:#0f766e}
    div[data-testid="stMetricValue"] * {color:#0f766e !important}
    </style>
    """,
    unsafe_allow_html=True,
)


def _collect_services(infra: Infrastructure, group: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for svc in infra.filter_by_group(group):
        bundle = infra.get_bundle_by_service(svc)
        if not bundle:
            continue
        cfg = infra.get_service_config(svc)
        entries.append(
            {
                "bundle": bundle,
                "service": svc,
                "config": cfg,
                "server": bundle.name,
                "ip": bundle.server.ip,
                "name": svc.name,
                "state": svc.state,
                "path": svc.target_path,
                "links": svc.service_urls or {},
            }
        )
    return entries


def _state_label(state: str) -> str:
    mapping = {
        "running": "🟢 Running",
        "stopped": "🔴 Stopped",
        "un-initialized": "⚪ Pending",
        "unknown": "🟠 Unknown",
    }
    return mapping.get(state, state)


def _render_section(
    label: str, entries: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    st.subheader(label)
    if not entries:
        st.info(f"No {label.lower()} detected yet.")
        return None

    total = len(entries)
    running = sum(1 for e in entries if e["state"] == "running")
    stopped = sum(1 for e in entries if e["state"] == "stopped")
    pending = sum(1 for e in entries if e["state"] == "un-initialized")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", total)
    c2.metric("Running", running)
    c3.metric("Stopped", stopped)
    c4.metric("Pending", pending)

    table_rows = []
    for entry in entries:
        links = entry["links"]
        primary_link = next(iter(links.values()), "")
        table_rows.append(
            {
                "Service": entry["name"],
                "Server": entry["ip"],
                "State": _state_label(entry["state"]),
                "Path": entry["path"],
                "Open": primary_link,
            }
        )
    df = pd.DataFrame(table_rows)
    selection = st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "Open": st.column_config.LinkColumn(display_text="Open"),
            "Service": st.column_config.TextColumn(help="Service name"),
            "Server": st.column_config.TextColumn(help="Server IP"),
            "Path": st.column_config.TextColumn(help="Target path"),
        },
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        return entries[idx]
    return None


def models():
    st.markdown("## Model Operations")
    st.caption(
        "Track deployed model servers and registries. Select a row for advanced settings."
    )

    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    served_models = _collect_services(infra, "model-server")
    registries = _collect_services(infra, "model-registry")

    total_models = len(served_models)
    total_registries = len(registries)
    total_running = sum(
        1 for svc in served_models + registries if svc["state"] == "running"
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Served Models", total_models)
    col2.metric("Registries", total_registries)
    col3.metric("Running Total", total_running)

    served_tab, registry_tab = st.tabs(["Served Models", "Registries"])
    selected_entry: Optional[Dict[str, Any]] = None
    with served_tab:
        selected_entry = _render_section("Served Models", served_models)
    with registry_tab:
        registry_selection = _render_section("Model Registries", registries)
        selected_entry = selected_entry or registry_selection

    if selected_entry:
        service = selected_entry["service"]
        bundle = selected_entry["bundle"]
        config = selected_entry["config"]
        st.markdown("----")
        st.markdown(f"### {service.name} settings")
        if config:
            callable_settings_func = config.instantiate_ui("settings")
            if callable_settings_func and service.state == "running":
                callable_settings_func(infra, bundle, service)
            else:
                st.info("Service must be running to show configuration details.")
        else:
            st.warning("No configuration metadata found for this service.")


models()
