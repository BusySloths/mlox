import pandas as pd  # type: ignore
import streamlit as st

from typing import cast

from mlox.session import MloxSession
from mlox.config import load_all_service_configs
from mlox.secret_manager import AbstractSecretManagerService
from mlox.view.logs import show_service_logs_ui


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


def save_infra():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


def _state_badge(state: str) -> str:
    colors = {
        "running": "#16a34a",
        "stopped": "#ef4444",
        "un-initialized": "#64748b",
        "unknown": "#f59e0b",
    }
    return f"<span class='svc-badge' style='background:{colors.get(state, '#64748b')}'>{state}</span>"


def _chip(text: str, color: str | None = None) -> str:
    style = f"background:{color};color:#0b1220;border:0;" if color else ""
    return f"<span class='svc-chip' style='{style}'>{text}</span>"


def _color_for(label: str) -> str:
    palette = [
        "#d8b4fe",
        "#fde68a",
        "#a7f3d0",
        "#93c5fd",
        "#fca5a5",
        "#c7d2fe",
        "#fdba74",
        "#86efac",
        "#f9a8d4",
        "#bfdbfe",
    ]
    return palette[sum(ord(c) for c in label) % len(palette)]


def installed_services():
    # Header: concise, visually clear intro + legend and guide
    # st.markdown("## Installed Services 🧭")
    st.caption(
        (
            "Browse, filter, and manage your installed services. Select a row for actions and settings.\n"
            "A service is a deployable component (e.g., MLflow, Airflow, Redis) that runs on or is associated "
            "with one of your servers.\n"
            "Add new services in the “Templates” tab: choose a backend and server, tweak settings, "
            "then click “Add Service”."
        )
    )
    infra = None
    try:
        session = cast(MloxSession, st.session_state.mlox)
        infra = session.infra
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    services = []
    for bundle in infra.bundles:
        for s in bundle.services:
            cfg = infra.get_service_config(s)
            services.append(
                {
                    "bundle": bundle,
                    "service": s,
                    "ip": bundle.server.ip,
                    "name": s.name,
                    "version": getattr(cfg, "version", ""),
                    "links": s.service_urls or {},
                    "state": s.state,
                    "uuid": s.uuid,
                    "groups": list(getattr(cfg, "groups", {}).keys()) if cfg else [],
                }
            )

    if not services:
        st.info("No services installed yet. Switch to the Templates tab to add one.")
        return

    # Summary + filters
    running = sum(1 for s in services if s["state"] == "running")
    stopped = sum(1 for s in services if s["state"] == "stopped")
    pending = sum(1 for s in services if s["state"] == "un-initialized")
    unknown = sum(1 for s in services if s["state"] == "unknown")
    total = len(services)
    sm1, sm2, sm3, sm4, sm5 = st.columns(5)
    sm1.metric("Total", total)
    sm2.metric("Running", running)
    sm3.metric("Stopped", stopped)
    sm4.metric("Pending", pending)
    sm5.metric("Unknown", unknown)

    f1, f2, f3 = st.columns([2, 1, 1])
    q = f1.text_input("Search services", value="", placeholder="Search by name or IP…")
    state_options = ["all", "running", "stopped", "un-initialized", "unknown"]
    state_sel = f2.selectbox("State", state_options, index=0)
    srv_sel = f3.selectbox(
        "Server",
        ["all"] + sorted({s["ip"] for s in services}),
        index=0,
    )

    filtered = services
    if q:
        ql = q.lower()
        filtered = [s for s in filtered if ql in s["name"].lower() or ql in s["ip"]]
    if state_sel != "all":
        filtered = [s for s in filtered if s["state"] == state_sel]
    if srv_sel != "all":
        filtered = [s for s in filtered if s["ip"] == srv_sel]

    if not filtered:
        st.caption("No services match your filters.")
        return

    # Build a dataframe view with colorful elements using emojis and LinkColumn
    def _state_emoji(s: str) -> str:
        return {
            "running": "🟢 Running",
            "stopped": "🔴 Stopped",
            "un-initialized": "⚪ Pending",
            "unknown": "🟠 Unknown",
        }.get(s, s)

    df_rows = []
    for ent in filtered:
        links_dict = ent.get("links", {}) or {}
        # pick a primary link if available
        primary_url = ""
        if links_dict:
            prefs = ["UI", "Dashboard", "Service", "Repository"]
            for p in prefs:
                if p in links_dict:
                    primary_url = links_dict[p]
                    break
            if not primary_url:
                primary_url = next(iter(links_dict.values()))
        df_rows.append(
            {
                "Name": ent["name"],
                "Version": ent["version"],
                "Server": ent["ip"],
                "State": _state_emoji(ent["state"]),
                "Groups": ", ".join(ent.get("groups", [])),
                "Open": primary_url,
            }
        )

    df = pd.DataFrame(df_rows)
    sel = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "Open": st.column_config.LinkColumn(display_text="Open"),
            "Name": st.column_config.TextColumn(help="Service name"),
            "Version": st.column_config.TextColumn(
                help="Service version", width="small"
            ),
            "Server": st.column_config.TextColumn(help="Server IP"),
            "State": st.column_config.TextColumn(help="Current state"),
            "Groups": st.column_config.TextColumn(help="Service groups/tags"),
        },
    )

    # Details + actions for selected row
    rows = sel.get("selection", {}).get("rows", [])
    if rows:
        idx = rows[0]
        entry = filtered[idx]
        svc = entry["service"]
        bndl = entry["bundle"]
        cfg = infra.get_service_config(svc)

        st.markdown("---")
        st.markdown(f"#### {svc.name}")
        b1, b2, b3, b4, b5, b_dump, b6, b7 = st.columns(
            [1, 1, 1, 3, 1, 1.5, 1, 1.5], gap="small", vertical_alignment="bottom"
        )
        if b_dump.button("Dump State", key=f"export-{svc.uuid}"):
            with bndl.server.get_server_connection() as conn:
                svc.dump_state(conn)
                st.success(f"Dumped state of {svc.name} to target directory.")
        if b6.button(
            "Setup",
            key=f"setup-{svc.uuid}",
            disabled=svc.state != "un-initialized",
            type="primary",
        ):
            with st.spinner(f"Setting up {svc.name}…", show_time=True):
                infra.setup_service(svc)
            save_infra()
            st.rerun()
        if b1.button(
            "Resume",
            key=f"start-{svc.uuid}",
            disabled=svc.state == "running" or svc.state == "un-initialized",
        ):
            with bndl.server.get_server_connection() as conn:
                svc.spin_up(conn)
            save_infra()
            st.rerun()
        if b2.button("Pause", key=f"stop-{svc.uuid}", disabled=svc.state != "running"):
            with bndl.server.get_server_connection() as conn:
                svc.spin_down(conn)
            save_infra()
            st.rerun()
        if b3.button("Check", key=f"check-{svc.uuid}"):
            with bndl.server.get_server_connection() as conn:
                status = svc.check(conn)
            st.toast(f"{svc.name} status: {status}")
        if b7.button("Teardown", key=f"teardown-{svc.uuid}", type="primary"):
            with st.spinner(f"Deleting {svc.name}…", show_time=True):
                infra.teardown_service(svc)
            save_infra()
            st.rerun()

        new_name = b4.text_input(
            "Rename",
            value=svc.name,
            key=f"rename-{svc.uuid}",
            label_visibility="collapsed",
        )
        # st_hack_align(r2)
        if b5.button("Rename", key=f"apply-{svc.uuid}") and new_name != svc.name:
            if new_name in infra.list_service_names():
                st.error("Service name must be unique.")
            else:
                svc.name = new_name
                save_infra()
                st.rerun()

        # Helpful links
        links = entry.get("links", {}) or {}
        if links:
            st.caption("Links")
            lcols = st.columns(4)
            i = 0
            for label, url in links.items():
                lcols[i % 4].link_button(label, url, use_container_width=True)
                i += 1

        callable_settings_func = cfg.instantiate_ui("settings") if cfg else None
        if callable_settings_func and svc.state == "running":
            with st.expander("Settings"):
                if isinstance(svc, AbstractSecretManagerService) and st.button(
                    "Set as default secret manager",
                    icon=":material/key:",
                    key=f"set-sm-{svc.uuid}",
                ):
                    session.set_secret_manager(svc.get_secret_manager(infra))
                    save_infra()
                    st.success(f"Set {svc.name} as default secret manager.")
                callable_settings_func(infra, bndl, svc)

        # Show logs UI when the service is running and the service template
        # supports a Docker backend. We prefer configuration-based detection
        # (service config groups) but also accept server-backed Docker deployments.
        backend_keys = []
        if cfg:
            backend_keys = list(cfg.groups.get("backend", {}).keys())
        server_backends = getattr(bndl.server, "backend", []) or []

        if svc.state == "running" and (
            "docker" in backend_keys or "docker" in server_backends
        ):
            with st.expander("Logs & History", expanded=False):
                tab_logs, tab_history = st.tabs(["Logs", "History"])
                with tab_history:
                    df_hist = pd.DataFrame(svc.exec.history)
                    if df_hist.empty:
                        st.info("No history available yet.")
                    else:
                        st.dataframe(
                            df_hist,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "timestamp": st.column_config.TextColumn(
                                    "Timestamp", width="small"
                                ),
                                "action": st.column_config.TextColumn("Action"),
                                "status": st.column_config.TextColumn(
                                    "Status", width="small"
                                ),
                                "metadata": st.column_config.TextColumn("Metadata"),
                            },
                        )
                with tab_logs:
                    show_service_logs_ui(session, svc.name)


def available_services():
    st.markdown("### Templates")
    infra = None
    try:
        session = cast(MloxSession, st.session_state.mlox)
        infra = session.infra
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    configs = load_all_service_configs()

    services = []
    for service in configs:
        services.append(
            {
                "name": service.name,
                "version": service.version,
                "maintainer": service.maintainer,
                "description": service.description,
                "description_short": service.description_short,
                "links": service.links,
                "requirements": service.requirements,
                "ui": list(service.ui.keys()),
                "groups": [
                    k for k in service.groups.keys() if k not in {"backend", "service"}
                ],
                "backend": list(service.groups.get("backend", {}).keys()),
                "config": service,
            }
        )

    c1, c2, _ = st.columns(3)
    search_filter = c1.text_input(
        "Search",
        value="",
        key="search_filter",
        label_visibility="collapsed",
        placeholder="Search for services...",
    )
    if search_filter:
        services = [s for s in services if search_filter.lower() in s["name"].lower()]

    option_map = {0: "Docker only", 1: "Kubernetes only"}
    selection = c2.pills(
        "Backend Filter",
        options=option_map.keys(),
        format_func=lambda option: option_map[option],
        selection_mode="single",
        default=None,
        label_visibility="collapsed",
    )
    if selection is not None:
        if selection == 0:
            services = [s for s in services if "docker" in s["backend"]]
        elif selection == 1:
            services = [s for s in services if "kubernetes" in s["backend"]]

    grid_cols = st.columns(3)
    for i, svc in enumerate(services):
        col = grid_cols[i % 3]
        with col.container(border=True):
            st.markdown(f"**{svc['name']}** · v{svc['version']}")
            if svc.get("description_short"):
                st.caption(svc["description_short"])
            chips = "".join(_chip(g, _color_for(g)) for g in svc.get("groups", []))
            st.markdown(chips, unsafe_allow_html=True)

            config = svc["config"]
            supported_backends = list(config.groups.get("backend", {}).keys())

            # Show supported backends as info
            if supported_backends:
                st.caption(f"Backends: {', '.join(supported_backends)}")

            if st.button(
                "Add Service",
                type="primary",
                key=f"add-{i}",
                use_container_width=True,
            ):
                _show_add_service_dialog(infra, config, supported_backends)

    # Handle the add service dialog
    if "show_add_dialog" in st.session_state and st.session_state.show_add_dialog:
        _render_add_service_dialog()


def _show_add_service_dialog(infra, config, supported_backends):
    """Store dialog state and trigger dialog display."""
    st.session_state.show_add_dialog = True
    st.session_state.dialog_config = config
    st.session_state.dialog_backends = supported_backends
    st.session_state.dialog_infra = infra
    st.rerun()


@st.dialog("Add Service")
def _render_add_service_dialog():
    """Render the add service dialog with backend/server selection and configuration."""
    if not st.session_state.get("show_add_dialog", False):
        return

    config = st.session_state.get("dialog_config")
    supported_backends = st.session_state.get("dialog_backends", [])
    infra = st.session_state.get("dialog_infra")

    if not config or not infra:
        st.error("Dialog configuration error")
        return

    st.markdown(f"**{config.name}** · v{config.version}")
    if config.description:
        st.markdown(config.description)

    # Backend selection
    selected_backend = st.selectbox(
        "Backend",
        supported_backends,
        disabled=len(supported_backends) <= 1,
        key="dialog_backend",
    )

    # Server selection
    bundle_candidates = infra.filter_bundles_by_backend(backend=selected_backend)
    running_bundles = [b for b in bundle_candidates if b.server.state == "running"]

    if not running_bundles:
        st.warning(f"No running servers found with {selected_backend} backend")
        if st.button("Cancel"):
            st.session_state.show_add_dialog = False
            st.rerun()
        return

    selected_bundle = st.selectbox(
        "Server",
        running_bundles,
        format_func=lambda x: f"{x.name} ({x.server.ip})",
        key="dialog_server",
    )

    # Configuration parameters
    params = {}
    callable_setup_func = config.instantiate_ui("setup")
    if callable_setup_func and selected_bundle:
        st.markdown("**Configuration**")
        params = callable_setup_func(infra, selected_bundle)

    # Action buttons
    col1, col2 = st.columns(2)

    if col1.button("Add Service", type="primary", use_container_width=True):
        if selected_bundle:
            with st.spinner(f"Adding {config.name}..."):
                ret = infra.add_service(selected_bundle.server.ip, config, params or {})
                if ret:
                    st.success(
                        f"Successfully added {config.name} to {selected_bundle.name}"
                    )
                    save_infra()
                    st.session_state.show_add_dialog = False
                    st.rerun()
                else:
                    st.error("Failed to add service")

    with col2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.show_add_dialog = False
            st.rerun()


# Tabs layout
tab_installed, tab_avail = st.tabs(["Installed", "Templates"])
with tab_avail:
    available_services()

with tab_installed:
    installed_services()
