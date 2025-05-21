import streamlit as st

from typing import cast

from mlox.infra import Infrastructure
from mlox.view.utils import form_add_server


def tab_server_mngmt():
    infra = cast(Infrastructure, st.session_state.mlox.infra)

    # with st.expander("Add Server"):
    st.write("To add a server, use the form below.")
    with st.form(key="add_new_server"):
        ip, port, root, pw, config = form_add_server()
        if st.form_submit_button(label="Add Server"):
            bundle = infra.add_server(
                config,
                {
                    "${MLOX_IP}": ip,
                    "${MLOX_PORT}": str(port),
                    "${MLOX_ROOT}": root,
                    "${MLOX_ROOT_PW}": pw,
                },
            )
            if not bundle:
                st.error("Uh oh, something went wrong. ")
            else:
                st.info(f"Server added successfully: {ip}")
                st.rerun()

    st.markdown("### Server List")

    srv = []
    for bundle in infra.bundles:
        info = bundle.server.get_server_info()
        srv.append(
            {
                "ip": bundle.server.ip,
                "name": bundle.name,
                "status": [bundle.status],
                "tags": bundle.tags,
                "services": [s.service.name for s in bundle.services],
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

        # server_management(infra, selected_server)
        c1, c2, c3 = st.columns([40, 50, 10])
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
        if c3.button("Update", type="primary"):
            bundle.name = name
            bundle.tags = tags
            st.rerun()

        c1, c2, _, c3, c4, c5, c6 = st.columns([10, 10, 15, 15, 15, 20, 15])
        if c1.button("Delete", type="primary"):
            st.info(f"Server with IP {selected_server} will be deleted.")
            infra.delete_bundle(bundle)
            st.rerun()
        if c2.button("Initialize", disabled=bundle.status != "un-initialized"):
            st.info(f"Initialize the server with IP {selected_server}.")
            with st.spinner("Initializing server...", show_time=True):
                bundle.initialize()
            st.rerun()
        if c3.button("Setup Docker", disabled=bundle.status != "no-backend"):
            st.info(f"Change the backend for server with IP {selected_server}.")
            with st.spinner("Enabling docker backend...", show_time=True):
                bundle.set_backend("docker")
            st.rerun()
        if c4.button("Setup K8S", disabled=bundle.status != "no-backend"):
            st.info(f"Change the backend for server with IP {selected_server}.")
            with st.spinner("Enabling k8s backend...", show_time=True):
                bundle.set_backend("kubernetes")
            st.rerun()
        controller = c5.selectbox(
            "K8s controller",
            infra.list_kubernetes_controller(),
            format_func=lambda x: x.name,
        )
        if c6.button("Setup K8S-Agent", disabled=bundle.status != "no-backend"):
            # st.write(controller)
            with st.spinner(
                f"setting up k8s-agent backend with controller {controller.name}.",
                show_time=True,
            ):
                bundle.set_backend("kubernetes-agent", controller=controller)
            st.rerun()

        with st.expander("Terminal"):
            from mlox.view.terminal import emulate_basic_terminal

            with bundle.server.get_server_connection() as conn:
                emulate_basic_terminal(conn)

        with st.expander("More info"):
            from mlox.remote import exec_command

            with bundle.server.get_server_connection() as conn:
                st.write(exec_command(conn, "ufw status", sudo=True))

            st.write(bundle.server.get_docker_status())
            st.write(bundle.server.get_kubernetes_status())
            st.write(bundle)


st.header("Server Management")
st.write(
    "This is a simple server management interface. You can add servers, manage services, and view server information."
)
tab_server_mngmt()

st.divider()
if st.button("Save Infrastructure"):
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()
