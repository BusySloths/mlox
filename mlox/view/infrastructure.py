import logging
import pandas as pd
import streamlit as st

from typing import cast, List, Dict, Any

from mlox.infra import Infrastructure
from mlox.config import load_all_server_configs
from mlox.view.utils import plot_config_nicely

logger = logging.getLogger(__name__)


def save_infra():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


# Lightweight chips styling to match Services templates
st.markdown(
    """
    <style>
    .svc-chip {display:inline-block;padding:2px 8px;border-radius:999px;background:#111827;color:#e5e7eb;margin-right:6px;margin-bottom:4px;font-size:12px;border:1px solid #374151}
    .svc-table {width:100%;border-collapse:separate;border-spacing:0 6px}
    .svc-table th {text-align:left;padding:8px 10px;color:#94a3b8;font-size:13px}
    .svc-table td {background:#0b1220;padding:10px;border-top:1px solid #1f2937;border-bottom:1px solid #1f2937}
    .svc-pill {display:inline-block;padding:2px 6px;border:1px solid #334155;border-radius:6px;color:#cbd5e1;font-size:12px}
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


def _state_emoji(state: str) -> str:
    mapping = {
        "running": "🟢 Running",
        "stopped": "🔴 Stopped",
        "starting": "🔵 Starting",
        "un-initialized": "⚪ Pending",
        "unknown": "🟠 Unknown",  # Blue for unknown state
    }
    return mapping.get(state, state)


def format_groups(groups: Dict[str, Any]) -> List[str]:
    group_list: List[str] = list()
    for k, v in groups.items():
        if isinstance(v, Dict):
            group_list.extend([f"{k}:{e}" for e in format_groups(v)])
        else:
            group_list.append(f"{k}:{v}" if v else k)
    return group_list


# @st.fragment(run_every="30s")
def check_server_status(server):
    try:
        _ = server.test_connection()
        _ = server.get_server_info(no_cache=True)
    except Exception as e:
        logger.warning(f"Could not get server info: {e}")


@st.cache_data
def get_server_infos(infra: Infrastructure) -> List[Dict[str, Any]]:
    configs = load_all_server_configs()
    servers = []
    for service in configs:
        servers.append(
            {
                "name": service.name,
                "version": service.version,
                "maintainer": service.maintainer,
                "description": service.description,
                "description_short": service.description_short,
                "links": [f"{k}: {v}" for k, v in service.links.items()],
                "requirements": [f"{k}: {v}" for k, v in service.requirements.items()],
                "ui": [f"{k}" for k, v in service.ui.items()],
                # "groups": [f"{k}" for k, v in service.groups.items() if k != "backend"],
                "groups": format_groups(service.groups),
                "backend": [
                    f"{k}" for k, v in service.groups.get("backend", {}).items()
                ],
                "config": service,
            }
        )
    return servers


def tab_server_management(infra: Infrastructure):
    # st.markdown("### Server List")
    st.caption(
        """Manage your servers and view their status. Select a server row to see details and perform actions.
        A server is a physical or virtual machine (e.g., Ubuntu VM, Kubernetes cluster) that can host one or more services.
        Add new servers in the “Templates” tab: choose a backend, tweak settings, then click “Add Server”."""
    )
    # Build rows + metrics
    rows = []
    running = stopped = pending = unknown = 0
    total_services = 0
    cpu_sum = 0
    ram_sum = 0.0
    storage_sum = 0.0
    for bundle in infra.bundles:
        state = bundle.server.state
        info = bundle.server.get_server_info()
        total_services += len(bundle.services)
        try:
            cpu_sum += int(info.get("cpu_count", 0) or 0)
            ram_sum += float(info.get("ram_gb", 0) or 0)
            storage_sum += float(info.get("storage_gb", 0) or 0)
        except Exception:
            pass
        if state == "running":
            running += 1
        elif state == "stopped":
            stopped += 1
        elif state == "un-initialized":
            pending += 1
        else:
            unknown += 1
        rows.append(
            {
                "ip": bundle.server.ip,
                "name": bundle.name,
                "backend": bundle.server.backend,
                "status": state,
                "tags": bundle.tags,
                "discovered": bundle.server.discovered,
                "services": [s.name for s in bundle.services],
                "hostname": info.get("host", ""),
                "specs": (
                    f"{info.get('cpu_count', '?')} CPUs, {info.get('ram_gb', '?')} GB RAM, "
                    f"{info.get('storage_gb', '?')} GB Storage, {info.get('pretty_name', '')}"
                ),
            }
        )

    # Summary metrics
    total_servers = len(infra.bundles)
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Servers", total_servers)
    m2.metric("Running", running)
    m3.metric("Stopped", stopped)
    m4.metric("Pending", pending)
    m5.metric("Services", total_services)
    m6.metric("CPU/RAM/Storage", f"{cpu_sum} • {ram_sum:.0f}GB • {storage_sum:.0f}GB")

    # Colorful dataframe using emojis; Tags rendered as plain text with emoji pills
    df_rows = []
    for r in rows:
        tags = r.get("tags", []) or []
        df_rows.append(
            {
                "Name": r["name"],
                "IP": r["ip"],
                "Backend": ", ".join(r.get("backend", []))
                if isinstance(r.get("backend"), list)
                else r.get("backend", ""),
                "State": _state_emoji(r["status"]),
                "Tags": r.get("tags", []),
                "Services": len(r.get("services", [])),
                "Host": r.get("hostname", ""),
                "Specs": r.get("specs", ""),
            }
        )
    df = pd.DataFrame(df_rows)
    select_server = st.dataframe(
        df,
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="server-select",
        column_config={
            "Name": st.column_config.TextColumn(help="Server display name"),
            "IP": st.column_config.TextColumn(help="Server address"),
            "Backend": st.column_config.TextColumn(help="Enabled backends"),
            "State": st.column_config.TextColumn(help="Current status"),
            # "Tags": st.column_config.TextColumn(help="Server tags", width="medium"),
            "Services": st.column_config.NumberColumn(
                help="# of services", width="small"
            ),
            "Host": st.column_config.TextColumn(help="Hostname"),
            "Specs": st.column_config.TextColumn(help="CPU, RAM, Storage, OS"),
        },
    )

    if len(select_server["selection"].get("rows", [])) == 1:
        selected_server = rows[select_server["selection"]["rows"][0]]["ip"]
        bundle_tmp = infra.get_bundle_by_ip(str(selected_server))
        if not bundle_tmp:
            st.error(f"Could not find bundle for server {selected_server}.")
            return
        bundle = bundle_tmp

        # server_management(infra, selected_server)
        c1, c2, c3 = st.columns([30, 55, 15])
        name = c1.text_input("Name", value=bundle.name)
        tags = c2.multiselect(
            "Tags",
            options=["prod", "dev"] + bundle.tags,
            default=bundle.tags,
            placeholder="Enter the server tags (comma-separated)",
            help="Tags to categorize the server.",
            accept_new_options=True,
            max_selections=10,
        )
        c3.write('<div style="height: 28px;"></div>', unsafe_allow_html=True)

        if c3.button("Update", type="primary", help="Update", icon=":material/update:"):
            bundle.name = name
            bundle.tags = tags
            save_infra()
            st.rerun()

        c1, c2, c3, _, c4, c5, c6 = st.columns([10, 15, 10, 17, 18, 15, 25])
        if c4.button("Refresh Status", icon=":material/refresh:"):
            with st.spinner("Refreshing server status...", show_time=True):
                check_server_status(bundle.server)
                save_infra()
                st.rerun()

        if c2.button("Delete", type="primary"):
            st.info(f"Backend for server with IP {selected_server} will be deleted.")
            infra.remove_bundle(bundle)
            save_infra()
            st.rerun()

        # if c2.button("Clear Backend", disabled=bundle.server.state != "running"):
        #     st.info(f"Backend for server with IP {selected_server} will be cleared.")
        #     bundle.server.teardown_backend()
        #     save_infra()
        #     st.rerun()
        if c1.button("Setup", disabled=not bundle.server.state == "un-initialized"):
            st.info(f"Initialize the server with IP {selected_server}.")
            with st.spinner("Initializing server...", show_time=True):
                bundle.server.setup()
            save_infra()
            st.rerun()
        current_access = "mlox.debug" in bundle.tags
        if (
            c6.toggle(":material/bug_report: Enable debug access", current_access)
            != current_access
        ):
            if current_access:
                # remove access
                st.info("Remove debug access")
                bundle.tags.remove("mlox.debug")
                bundle.server.disable_debug_access()
            else:
                # enable access
                st.info("Enable debug access")
                bundle.tags.append("mlox.debug")
                bundle.server.enable_debug_access()
            save_infra()
            st.rerun()

        with st.container(border=True):
            config = infra.get_service_config(bundle.server)
            if config:
                plot_config_nicely(
                    config,
                    prefix_name=bundle.name + " - ",
                    additional_badges={
                        f"service:{s.name}": None for s in bundle.services
                    },
                )

                callable_settings_func = config.instantiate_ui("settings")
                if callable_settings_func:
                    callable_settings_func(infra, bundle, bundle.server)

        with st.expander("History", expanded=True):
            df_hist = pd.DataFrame(bundle.server.exec.history)
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
                        "status": st.column_config.TextColumn("Status", width="small"),
                        "metadata": st.column_config.TextColumn("Metadata"),
                    },
                )

            # with st.expander("Terminal"):
            #     from mlox.view.terminal import emulate_basic_terminal

            #     with bundle.server.get_server_connection() as conn:
            #         emulate_basic_terminal(conn)


def tab_server_templates(infra: Infrastructure):
    st.caption(
        """ Browse and add server templates. Select a backend, configure settings, then click "Add Server".
        A server is a physical or virtual machine (e.g., Ubuntu VM, Kubernetes cluster) that can host one or more services.
        After adding, manage servers and their services in the "Server Management" tab.
    """
    )
    servers = get_server_infos(infra)

    c1, c2, _ = st.columns(3)
    search_filter = c1.text_input(
        "Search",
        value="",
        key="server_search_filter",
        label_visibility="collapsed",
        placeholder="Search for servers...",
    )
    if search_filter:
        servers = [s for s in servers if search_filter.lower() in s["name"].lower()]

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
            servers = [s for s in servers if "docker" in s["backend"]]
        elif selection == 1:
            servers = [s for s in servers if "kubernetes" in s["backend"]]

    # Cards grid similar to Services templates
    cols = st.columns(3)
    for i, srv in enumerate(servers):
        col = cols[i % 3]
        with col.container(border=True):
            st.markdown(f"**{srv['name']}** · v{srv['version']}")
            if srv.get("description_short"):
                st.caption(srv["description_short"])
            chips = "".join(_chip(g, _color_for(g)) for g in srv.get("groups", []))
            st.markdown(chips, unsafe_allow_html=True)

            config = srv["config"]

            params: Dict[str, Any] | None = {}
            callable_setup_func = config.instantiate_ui("setup")
            if callable_setup_func:
                with st.expander("", icon=":material/settings:"):
                    params = callable_setup_func(infra, config)

            if st.button(
                "Add Server",
                icon=":material/computer:",
                type="primary",
                key=f"add-server-{i}",
                disabled=params is None,
            ):
                st.info(f"Adding server {config.name} {config.version}.")
                ret = infra.add_server(config, params or {})
                if not ret:
                    st.error("Failed to add server")
                save_infra()


# tab_avail, tab_installed = st.tabs(["Templates", "Server Management"])
tab_installed, tab_avail = st.tabs(["Server Management", "Templates"])
infra = None
try:
    infra = cast(Infrastructure, st.session_state.mlox.infra)
except BaseException:
    st.error("Could not load infrastructure configuration.")
    st.stop()


with tab_avail:
    tab_server_templates(infra)

with tab_installed:
    tab_server_management(infra)
