import streamlit as st

from mlox.server import Ubuntu


def tab_server_list():
    infra = st.session_state.mlox.infra
    # with st.expander("Add Server"):
    st.write("To add a server, use the form below.")
    with st.form(key="add_server"):
        c1, c2 = st.columns([70, 30])
        ip = c1.text_input(
            "IP Address",
            placeholder="Enter the server IP address",
            help="The IP address of the server you want to add.",
        )
        port = c2.number_input(
            "SSH Port",
            value=22,
            min_value=1,
            max_value=65535,
            step=1,
            placeholder="Enter the server SSH port",
            help="The SSH port for the server.",
        )
        c1, c2 = st.columns(2)
        root = c1.text_input(
            "Root Account Name",
            value="root",
            placeholder="Enter the server root account name",
            help="Enter the server root account name.",
        )
        pw = c2.text_input(
            "Root Account Password",
            placeholder="Enter the server password",
            help="The password for the server.",
            type="password",
        )
        if st.form_submit_button(label="Add Server"):
            my_ubuntu = Ubuntu(ip, root, pw, port=str(port))
            stats = my_ubuntu.get_server_info()
            # system stats
            st.write(stats)
            # TODO check for compatibility (server and hardware)
            infra.add_server(my_ubuntu)
            st.info(f"Server added successfully: {ip}")

    st.markdown("### Server List")

    srv = []
    for bundle in infra.bundles:
        info = bundle.server.get_server_info()
        srv.append(
            {
                "ip": bundle.server.ip,
                "name": bundle.name,
                "backend": [bundle.backend],
                "tags": bundle.tags,
                "services": [s.name for s in bundle.services],
                "specs": f"{info['cpu_count']} CPUs, {info['ram_gb']} GB RAM, {info['storage_gb']} GB Storage, {info['pretty_name']}",
            }
        )
        if bundle.backend == "kubernetes":
            for node in bundle.cluster:
                info = node.get_server_info()
                srv.append(
                    {
                        "ip": bundle.server.ip,
                        "name": bundle.name,
                        "backend": [bundle.backend],
                        "tags": ["compute-node"] + bundle.tags,
                        "services": [s.name for s in bundle.services],
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

        c1, c2, c3, _ = st.columns([8, 15, 10, 65])
        if c1.button("Delete"):
            st.info(f"Server with IP {selected_server} will be deleted.")
            infra.delete_bundle(bundle)
            st.rerun()
        if c2.button("Switch Backend", disabled=bundle.backend == "un-initialized"):
            st.info(f"Change the backend for server with IP {selected_server}.")
            bundle.switch_backend()
            st.rerun()
        if c3.button("Initialize", disabled=bundle.backend != "un-initialized"):
            st.info(f"Initialize the server with IP {selected_server}.")
            with st.spinner("Initializing server...", show_time=True):
                bundle.initialize()
            st.rerun()

        st.write(bundle)

    if st.button("Save Infrastructure"):
        with st.spinner("Saving infrastructure..."):
            st.session_state.mlox.save_infrastructure()


def tab_cluster_overview():
    st.header("Cluster Overview")
    infra = st.session_state.mlox.infra

    cluster = []
    for bundle in infra.bundles:
        info = bundle.server.get_server_info()
        if bundle.backend != "kubernetes":
            continue
        cluster.append(
            {
                "controller": bundle.server.ip,
                "name": bundle.name,
                "backend": [bundle.backend],
                "tags": bundle.tags,
                "nodes": [s.name for s in bundle.cluster],
                "specs": f"{info['cpu_count']} CPUs, {info['ram_gb']} GB RAM, {info['storage_gb']} GB Storage, {info['pretty_name']}",
            }
        )

    select_server = st.dataframe(
        cluster,
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="cluster-select",
    )

    if len(select_server["selection"].get("rows", [])) == 1:
        selected_server = cluster[select_server["selection"]["rows"][0]]["controller"]
        bundle = infra.get_bundle_by_ip(selected_server)
        st.write(bundle)


tab_server, tab_k3s = st.tabs(["Server", "Cluster"])
with tab_server:
    st.header("Server Management")
    st.write(
        "This is a simple server management interface. You can add servers, manage services, and view server information."
    )
    tab_server_list()
with tab_k3s:
    st.header("Cluster Management")
    st.write(
        "This is a simple cluster management interface. You can add clusters, manage services, and view cluster information."
    )
    tab_cluster_overview()
