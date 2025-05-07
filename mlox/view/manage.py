import os
import streamlit as st

from mlox.infra import Infrastructure


@st.dialog("Server Management", width="large")
def server_management(infra, selected_server):
    st.write(f"Selected server: {selected_server}")
    bundle = infra.get_bundle_by_ip(selected_server)
    st.write(f"Bundle: {bundle.name}")
    st.write(f"Description: {bundle.descr}")
    st.write(f"Tags: {bundle.tags}")
    st.write(f"Services: {bundle.services}")
    st.write(f"Server: {bundle.server}")


@st.cache_data
def load_infrastructure():
    return Infrastructure.load(
        "/infrastructure.json", os.environ["MLOX_CONFIG_PASSWORD"]
    )


st.header("Server Management")
st.write(
    "This is a simple server management interface. You can add servers, manage services, and view server information."
)
st.write(
    "To add a server, click the button below. To manage a server, select it from the list."
)

st.markdown("### Available Server")


with st.popover("Add Server", use_container_width=False):
    st.text_input(
        "IP Address",
        placeholder="Enter the server IP address",
        help="The IP address of the server you want to add.",
    )

    st.text_input(
        "Root Account Name",
        value="root",
        placeholder="Enter the server root account name",
        help="Enter the server root account name.",
    )
    st.text_input(
        "Root Account Password",
        placeholder="Enter the server password",
        help="The password for the server.",
        type="password",
    )
    st.number_input(
        "SSH Port",
        value=22,
        min_value=1,
        max_value=65535,
        step=1,
        placeholder="Enter the server SSH port",
        help="The SSH port for the server.",
    )
    # st.divider()
    # st.write("The following fields are optional and can be edited later.")
    # st.text_input(
    #     "Name",
    #     placeholder="Give it a name",
    #     help="The name of the server you want to add.",
    # )
    # st.text_input(
    #     "Description",
    #     placeholder="Enter the server description",
    #     help="A brief description of the server.",
    # )
    # st.multiselect(
    #     "Server Tags",
    #     options=["prod", "dev"],
    #     placeholder="Enter the server tags (comma-separated)",
    #     help="Tags to categorize the server.",
    #     accept_new_options=True,
    #     max_selections=5,
    # )


infra = load_infrastructure()

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
    server_management(infra, selected_server)

st.markdown("### Docker Servers")
st.info("You currently have no docker servers.")

st.markdown("### Kubernetes Cluster")
st.info("You currently have no kubernetes cluster.")


if st.button("Save Infrastructure"):
    with st.spinner("Saving infrastructure..."):
        try:
            infra.save("./infrastructure_v2.json", os.environ["MLOX_CONFIG_PASSWORD"])
            st.success("Infrastructure saved successfully.")
        except Exception as e:
            st.error(f"Error saving infrastructure: {e}")

# if len(select_server["selection"].get("rows", [])) == 1:
#     selected_server = srv[select_server["selection"]["rows"][0]]["ip"]

# with st.popover(
#     "Add Service", use_container_width=False, disabled=selected_server is None
# ):
#     if selected_server is not None:
#         service = st.selectbox("Select service", [configure_and_add_airflow])
#         service(Infrastructure.get_instance().get_server_dict()[selected_server])


# infra = []
# for server in Infrastructure.get_instance().servers:
#     if selected_server is not None:
#         if selected_server != server.ip:
#             continue
#     for service in server.services:
#         infra.append(
#             {
#                 "ip": server.ip,
#                 "service": type(service),
#                 "is_installed": service.is_installed,
#                 "is_running": service.is_running,
#                 "service_url": service.service_url,
#             }
#         )
# select_service = st.dataframe(
#     infra,
#     use_container_width=True,
#     selection_mode="single-row",
#     hide_index=True,
#     on_select="rerun",
# )

# if len(select_service["selection"].get("rows", [])) == 1:
#     service_ip = infra[select_service["selection"]["rows"][0]]["ip"]
#     service_type = infra[select_service["selection"]["rows"][0]]["service"]
#     server = Infrastructure.get_instance().get_server_dict()[service_ip]
#     service = Infrastructure.get_instance().get_service_by_ip_and_type(
#         service_ip, service_type
#     )
#     if service is not None:
#         c1, c2, c3 = st.columns(3)
#         if c1.button("Setup"):
#             with server.get_server_connection() as conn:
#                 service.setup(conn)
#         if c2.button("Start"):
#             with server.get_server_connection() as conn:
#                 service.spin_up(conn)
#         if c3.button("Stop"):
#             with server.get_server_connection() as conn:
#                 service.spin_down(conn)

#         st.write(service)
