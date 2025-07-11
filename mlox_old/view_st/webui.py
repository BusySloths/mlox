import streamlit as st

from mlox_old.configs_old import (
    OpenWebUI,
    LiteLLM,
    get_server_connections,
    update_service,
    get_service_by_ip_and_type,
)
from mlox.remote import fs_read_file


st.set_page_config(page_title="OpenWebUI Install Page", page_icon="🌍")
st.markdown("# OpenWebUI Install")

servers = get_server_connections()
target_ip = st.selectbox("Choose Server", list(servers.keys()))
server = servers[target_ip]

my_litellm = get_service_by_ip_and_type(target_ip, LiteLLM)
if my_litellm is None:
    st.warning("Could not find LiteLLM configs. LiteLLM needs to be deployed first.")
    st.stop()

st.text_input("LiteLLM Path", my_litellm.target_path, disabled=True)

target_path = st.text_input("Install Path", f"/home/{server.user}/my_openwebui")
port = st.text_input("Port", "3000")
secret_key = st.text_input("Secret Key", "abc")
litellm_url = st.text_input("LiteLLM URL", f"{target_ip}:4000/v1")
litellm_key = st.text_input("LiteLLM API Key", "sk-1234")

service = OpenWebUI(
    server,
    target_path,
    port,
    secret_key,
    my_litellm.target_path,
    litellm_key,
    litellm_url,
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


files = [
    "docker-compose.yaml",
    "service.env",
    "cert.pem",
    "litellm.pem",
]
tabs = st.tabs(files)
for i in range(len(files)):
    with tabs[i]:
        with service.server as conn:
            res = fs_read_file(
                conn,
                f"{service.target_path}/{files[i]}",
                format="yaml" if files[i][-4:] == "yaml" else None,
            )
            if isinstance(res, str):
                st.text(res)
            else:
                st.write(res, unsafe_allow_html=True)
            print(res)

st.sidebar.header("Links")
st.sidebar.page_link(service.get_service_url(), label="OpenWebUI")
