import time
import pandas as pd
import streamlit as st

from typing import cast, List, Dict, Any

from mlox.infra import Infrastructure
from mlox.config import load_all_server_configs
from mlox.view.utils import plot_config_nicely


# def my_process(a_param):
#     print(f"my_process_{a_param}")
#     # takes a long time
#     time.sleep(10)
#     print(f"my_process_{a_param} done")
#     return 1, 2, a_param


# def my_callback(x, name):
#     print(f"my_callback_{x[2]}")
#     print(x)
#     print(name)


# if st.session_state.get("mlox", None) is not None:
#     scheduler = st.session_state.mlox.scheduler
#     scheduler.add(
#         process=my_process,
#         callback=my_callback,
#         params_process={"a_param": len(scheduler.queue) + 1},
#         params_callback={"name": "me"},
#     )


def save_infra():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


def format_groups(groups: Dict[str, Any]) -> List[str]:
    group_list: List[str] = list()

    for k, v in groups.items():
        if isinstance(v, Dict):
            group_list.extend([f"{k}:{e}" for e in format_groups(v)])
        else:
            group_list.append(f"{k}:{v}" if v else k)
    return group_list


@st.fragment(run_every="30s")
def auto_function(server):
    # This will update every 10 seconds!
    from datetime import datetime

    is_running = server.test_connection()
    st.write(
        f"Server {server.ip} is {'running :material/check: :material/cancel:' if is_running else 'not running'}. "
    )
    # st.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def server_management():
    infra = None
    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    st.markdown("### Server List")

    if len(infra.bundles) > 0:
        if st.button("Refresh"):
            for b in infra.bundles:
                if b.server.test_connection():
                    b.server.state = "running"
                else:
                    b.server.state = "unknown"
            save_infra()

    srv = []
    for bundle in infra.bundles:
        success = False
        info = {
            "host": "Unknown",
            "cpu_count": 0,
            "ram_gb": 0,
            "storage_gb": 0,
            "pretty_name": "Unknown",
        }
        try:
            info = bundle.server.get_server_info(no_cache=False)
            success = True
        except Exception as e:
            print(f"Could not get server info: {e}")

        srv.append(
            {
                "ip": bundle.server.ip,
                "name": bundle.name,
                "backend": bundle.server.backend,
                "status": [bundle.server.state if success else "error"],
                "tags": bundle.tags,
                "discovered": bundle.server.discovered,
                "services": [s.name for s in bundle.services],
                "hostname": info["host"],
                "specs": f"{info['cpu_count']} CPUs, {info['ram_gb']} GB RAM, {info['storage_gb']} GB Storage, {info['pretty_name']}",
            }
        )

    select_server = st.dataframe(
        srv,
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="server-select",
    )

    if len(select_server["selection"].get("rows", [])) == 1:
        selected_server = srv[select_server["selection"]["rows"][0]]["ip"]
        bundle = infra.get_bundle_by_ip(selected_server)

        # auto_function(bundle.server)

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

        c1, c2, c3, _, c4, c5, c6 = st.columns([10, 15, 10, 15, 15, 10, 25])
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

            # with st.expander("Terminal"):
            #     from mlox.view.terminal import emulate_basic_terminal

            #     with bundle.server.get_server_connection() as conn:
            #         emulate_basic_terminal(conn)

        with st.expander("More info"):
            #     from mlox.remote import exec_command

            #     with bundle.server.get_server_connection() as conn:
            #         st.write(exec_command(conn, "ufw status", sudo=True))

            st.write(bundle.server.get_backend_status())
        #     st.write(bundle.server.get_kubernetes_status())
        #     st.write(bundle)


def available_server_templates():
    st.markdown("""
    ### Available Server Templates
    This is where you can manage your server.""")
    infra = None
    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    # with st.expander("Add Server"):
    configs = load_all_server_configs()

    server = []
    for service in configs:
        server.append(
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

    c1, c2, _ = st.columns(3)
    search_filter = c1.text_input(
        "Search",
        value="",
        key="search_filter",
        label_visibility="collapsed",
        placeholder="Search for services...",
    )
    if len(search_filter) > 0:
        server = [s for s in server if search_filter.lower() in s["name"].lower()]

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
            server = [s for s in server if "docker" in s["backend"]]
        elif selection == 1:
            server = [s for s in server if "kubernetes" in s["backend"]]

    df = pd.DataFrame(server)
    select = st.dataframe(
        df[
            [
                "name",
                "version",
                # "maintainer",
                # "description",
                # "links",
                # "requirements",
                "backend",
                "groups",
                "description_short",
            ]
        ],
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="avail-server-select",
    )

    if len(select["selection"].get("rows", [])) == 1:
        selected = select["selection"]["rows"][0]

        config = server[selected]["config"]
        c2, c3, c4, _ = st.columns([25, 25, 15, 35])

        with st.container(border=True):
            plot_config_nicely(config)

            params = {}
            callable_setup_func = config.instantiate_ui("setup")
            if callable_setup_func:
                params = callable_setup_func(infra, config)

            if st.button("Add Server", icon=":material/computer:", type="primary"):
                # if st.form_submit_button(
                #     "Add Server", type="primary", icon=":material/computer:"
                # ):
                st.info(f"Adding server {config.name} {config.version}.")
                ret = infra.add_server(config, params)
                if not ret:
                    st.error("Failed to add server")
                save_infra()

        # st.write(server[selected])


# tab_avail, tab_installed = st.tabs(["Templates", "Server Management"])
tab_installed, tab_avail = st.tabs(["Server Management", "Templates"])

with tab_avail:
    available_server_templates()

with tab_installed:
    st.header("Server Management")
    st.write(
        "This is a simple server management interface. You can add servers, manage services, and view server information."
    )
    server_management()
