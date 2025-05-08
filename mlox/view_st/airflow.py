import streamlit as st
import uuid

from mlox.configs_old import Airflow


def configure_and_add_airflow(server):
    # st.set_page_config(page_title="Airflow Install Page", page_icon="🌍")
    # st.markdown("# Airflow Install")

    # servers = Infrastructure.get_instance().get_server_dict()
    # ip = st.selectbox("Choose Server", list(servers.keys()))
    # server = servers[ip]

    # target_path = st.text_input("Install Path", f"/home/{server.user}/my_airflow")
    # path_output = st.text_input("Airflow Output Path", f"{target_path}")
    path_dags = st.text_input(
        "DAGS Path", f"/home/{server.user}/Projects/flowprovider/flow"
    )
    target_path = f"/home/{server.user}/my_airflow"
    path_output = f"{target_path}"
    # secret_name = st.text_input("Secret Key", f"{server.ip}-my_airflow")
    # secret_path = str(uuid.uuid5(uuid.NAMESPACE_URL, secret_name))
    # st.write(f"Secret URL path: {secret_path}")
    secret_path = ""

    c1, c2, c3 = st.columns([40, 40, 20])
    ui_user = c1.text_input("Username", "admin")
    ui_pw = c2.text_input("Password", "admin0123")
    port = c3.text_input("Port", "7654")

    service = Airflow(
        target_path, path_dags, path_output, ui_user, ui_pw, port, secret_path
    )

    # c1, c2, c3, c4 = st.columns([15, 15, 15, 55])
    if st.button("Add Service"):
        server.add_service(service)
    # if c2.button("Setup"):
    #     service.setup()
    # if c2.button("Start"):
    #     service.spin_up()
    # if c3.button("Stop"):
    #     service.spin_down()


# with st.expander("Details"):
#     st.write(service)

# service_url = f"https://{server.ip}:{service.port}/{service.secret_path}"
# st.sidebar.header("Links")
# st.sidebar.page_link(service_url, label="Airflow")
