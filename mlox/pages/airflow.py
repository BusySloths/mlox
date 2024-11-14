import streamlit as st
import uuid

from mlox.configs import Airflow, get_servers, update_service


st.set_page_config(page_title="Airflow Install Page", page_icon="🌍")
st.markdown("# Airflow Install")

servers = get_servers()
target_ip = st.selectbox("Choose Server", list(servers.keys()))
server = servers[target_ip]

target_path = st.text_input("Install Path", f"/home/{server.user}/my_airflow")
path_dags = st.text_input(
    "DAGS Path", f"/home/{server.user}/Projects/flowprovider/flow"
)
path_output = st.text_input("Airflow Output Path", f"{target_path}")
port = st.text_input("Port", "7654")
secret_name = st.text_input("Secret Key", f"{target_ip}-my_airflow")
secret_path = str(uuid.uuid5(uuid.NAMESPACE_URL, secret_name))
st.write(f"Secret URL path: {secret_path}")

ui_user = st.text_input("Username", "admin")
ui_pw = st.text_input("Password", "admin0123")

service = Airflow(
    server,
    target_path,
    path_dags,
    path_output,
    ui_user,
    ui_pw,
    port,
    secret_path,
)
update_service(service)
c1, c2, c3, c4 = st.columns([15, 15, 15, 55])
if c1.button("Setup"):
    service.setup()
if c2.button("Start"):
    service.spin_up()
if c3.button("Stop"):
    service.spin_down()

with st.expander("Details"):
    st.write(service)

st.sidebar.header("Links")
st.sidebar.page_link(service.get_service_url(), label="Airflow")
