import streamlit as st
# from streamlit_navigation_bar import st_navbar

from dataclasses import asdict

from mlox.configs import Infrastructure
from mlox.view_st.server import add_server_to_infrastructure
from mlox.view_st.airflow import configure_and_add_airflow


# st.set_page_config(initial_sidebar_state="expanded")
# st.write("# Welcome to MLOX: MLOps-in-a-Box!")

with st.popover("Add Server", use_container_width=False):
    add_server_to_infrastructure()

srv = []
for server in Infrastructure.get_instance().servers:
    cpus, ram, storage = server.get_server_info()
    srv.append(
        {
            "ip": server.ip,
            "service": server.__class__.__name__,
            "specs": f"{int(cpus)} CPUs, {ram} GB RAM, {storage} GB Storage",
            "setup complete": server.setup_complete,
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

selected_server = None
if len(select_server["selection"].get("rows", [])) == 1:
    selected_server = srv[select_server["selection"]["rows"][0]]["ip"]

with st.popover(
    "Add Service", use_container_width=False, disabled=selected_server is None
):
    if selected_server is not None:
        service = st.selectbox("Select service", [configure_and_add_airflow])
        service(Infrastructure.get_instance().get_server_dict()[selected_server])


infra = []
for server in Infrastructure.get_instance().servers:
    if selected_server is not None:
        if selected_server != server.ip:
            continue
    for service in server.services:
        infra.append(
            {
                "ip": server.ip,
                "service": type(service),
                "is_installed": service.is_installed,
                "is_running": service.is_running,
                "service_url": service.service_url,
            }
        )
select_service = st.dataframe(
    infra,
    use_container_width=True,
    selection_mode="single-row",
    hide_index=True,
    on_select="rerun",
)

if len(select_service["selection"].get("rows", [])) == 1:
    service_ip = infra[select_service["selection"]["rows"][0]]["ip"]
    service_type = infra[select_service["selection"]["rows"][0]]["service"]
    server = Infrastructure.get_instance().get_server_dict()[service_ip]
    service = Infrastructure.get_instance().get_service_by_ip_and_type(
        service_ip, service_type
    )
    if service is not None:
        c1, c2, c3 = st.columns(3)
        if c1.button("Setup"):
            with server.get_server_connection() as conn:
                service.setup(conn)
        if c2.button("Start"):
            with server.get_server_connection() as conn:
                service.spin_up(conn)
        if c3.button("Stop"):
            with server.get_server_connection() as conn:
                service.spin_down(conn)

        st.write(service)
