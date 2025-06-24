import pandas as pd
import streamlit as st

from typing import cast

from mlox.infra import Infrastructure
from mlox.config import load_all_server_configs

from mlox.view.utils import form_add_server


def save_infra():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


@st.fragment(run_every="30s")
def auto_function(server):
    # This will update every 10 seconds!
    from datetime import datetime

    is_running = server.test_connection()
    st.write(
        f"Server {server.ip} is {'running :material/check: :material/cancel:' if is_running else 'not running'}. "
    )
    # st.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def tab_server_mngmt():
    infra = cast(Infrastructure, st.session_state.mlox.infra)

    # # with st.expander("Add Server"):
    # st.write("To add a server, use the form below.")
    # with st.form(key="add_new_server"):
    #     ip, port, root, pw, config = form_add_server()
    #     if st.form_submit_button(label="Add Server"):
    #         bundle = infra.add_server(
    #             config,
    #             {
    #                 "${MLOX_IP}": ip,
    #                 "${MLOX_PORT}": str(port),
    #                 "${MLOX_ROOT}": root,
    #                 "${MLOX_ROOT_PW}": pw,
    #             },
    #         )
    #         if not bundle:
    #             st.error("Uh oh, something went wrong. ")
    #         else:
    #             st.info(f"Server added successfully: {ip}")
    #             st.rerun()

    st.markdown("### Server List")

    srv = []
    for bundle in infra.bundles:
        info = bundle.server.get_server_info()
        srv.append(
            {
                "ip": bundle.server.ip,
                "name": bundle.name,
                "status": [bundle.server.state],
                "tags": bundle.tags,
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

        auto_function(bundle.server)

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
        if c3.button("Update", type="primary", help="Update", icon=":material/update:"):
            bundle.name = name
            bundle.tags = tags
            st.rerun()

        c1, c2, _, c3, c4, c5, c6 = st.columns([15, 10, 10, 15, 15, 10, 25])
        if c1.button("Clear Backend", type="primary"):
            st.info(f"Backend for server with IP {selected_server} will be cleared.")
            bundle.server.teardown_backend()
            st.rerun()
        if c2.button("Setup", disabled=bundle.server.state != "un-initialized"):
            st.info(f"Initialize the server with IP {selected_server}.")
            with st.spinner("Initializing server...", show_time=True):
                bundle.server.setup()
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
            st.rerun()

        # if c3.button("Setup Docker", disabled=bundle.status != "no-backend"):
        #     st.info(f"Change the backend for server with IP {selected_server}.")
        #     with st.spinner("Enabling docker backend...", show_time=True):
        #         bundle.set_backend("docker")
        #     st.rerun()
        # if c4.button("Setup K8S", disabled=bundle.status != "no-backend"):
        #     st.info(f"Change the backend for server with IP {selected_server}.")
        #     with st.spinner("Enabling k8s backend...", show_time=True):
        #         bundle.set_backend("kubernetes")
        #     st.rerun()
        # controller = c5.selectbox(
        #     "K8s controller",
        #     infra.list_kubernetes_controller(),
        #     format_func=lambda x: x.name,
        # )
        # if c6.button("Setup K8S-Agent", disabled=bundle.status != "no-backend"):
        #     # st.write(controller)
        #     with st.spinner(
        #         f"setting up k8s-agent backend with controller {controller.name}.",
        #         show_time=True,
        #     ):
        #         bundle.set_backend("kubernetes-agent", controller=controller)
        #     st.rerun()

        # with st.expander("Terminal"):
        #     from mlox.view.terminal import emulate_basic_terminal

        #     with bundle.server.get_server_connection() as conn:
        #         emulate_basic_terminal(conn)

        # with st.expander("More info"):
        #     from mlox.remote import exec_command

        #     with bundle.server.get_server_connection() as conn:
        #         st.write(exec_command(conn, "ufw status", sudo=True))

        #     st.write(bundle.server.get_docker_status())
        #     st.write(bundle.server.get_kubernetes_status())
        #     st.write(bundle)


def available_server_templates():
    st.markdown("""
    ### Available Server Templates
    This is where you can manage your server.""")
    infra = cast(Infrastructure, st.session_state.mlox.infra)

    # with st.expander("Add Server"):
    configs = load_all_server_configs("./stacks")

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
                "groups": [f"{k}" for k, v in service.groups.items() if k != "backend"],
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

        params = {}
        callable_setup_func = config.instantiate_ui("setup")
        if callable_setup_func:
            params = callable_setup_func(infra)

        if st.button("Add Server", type="primary"):
            st.info(f"Adding server {config.name} {config.version}.")
            ret = infra.add_server(config, params)
            if not ret:
                st.error("Failed to add server")
            save_infra()

        st.write(server[selected])


tab_avail, tab_installed = st.tabs(["Templates", "Servers"])
with tab_avail:
    available_server_templates()

with tab_installed:
    st.header("Server Management")
    st.write(
        "This is a simple server management interface. You can add servers, manage services, and view server information."
    )
    tab_server_mngmt()


st.divider()
if st.button("Save Infrastructure"):
    save_infra()
