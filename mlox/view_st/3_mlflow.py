import streamlit as st

from mlox.configs_old import MLFlow, Infrastructure
from mlox.remote import fs_read_file


st.set_page_config(page_title="MLFlow Install Page", page_icon="🌍")
st.markdown("# MLFlow Install")

servers = Infrastructure.get_instance().get_server_dict()
ip = st.selectbox("Choose Server", list(servers.keys()))
server = servers[ip]

target_path = st.text_input("Install Path", f"/home/{server.user}/my_mlflow")
port = st.text_input("Port", "1234")
ui_user = st.text_input("Username", "admin")
ui_pw = st.text_input("Password", "admin0123")

service = MLFlow(target_path, ui_user, ui_pw, port)

c1, c2, c3, c4 = st.columns([15, 15, 15, 55])
if c1.button("Add Service"):
    server.add_service(service)

# if c1.button("Setup"):
#     service.setup()
# if c2.button("Start"):
#     service.spin_up()
# if c3.button("Stop"):
#     service.spin_down()

with st.expander("Details"):
    st.write(service)

files = ["docker-compose.yaml", "service.env", "basic-auth.ini"]
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
st.sidebar.page_link(service.service_url, label="MLFlow")
