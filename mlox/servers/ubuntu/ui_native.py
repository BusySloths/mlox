import streamlit as st

from typing import Dict

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure, Bundle
from mlox.servers.ubuntu.native import UbuntuNativeServer


def form_add_server(sid: str):
    id = f"form-add-server-{sid}"
    # id = f"form-add-server-{random.randint(1000, 9999)}"
    # c1, c2 = st.columns(2)
    ip = st.text_input(
        "IP Address",
        placeholder="Enter the server IP address",
        help="The IP address of the server you want to add.",
        key=f"{id}-ip",
    )
    port = st.number_input(
        "SSH Port",
        value=22,
        min_value=1,
        max_value=65535,
        step=1,
        placeholder="Enter the server SSH port",
        help="The SSH port for the server.",
        key=f"{id}-port",
    )
    root = st.text_input(
        "Root",
        value="root",
        placeholder="Enter the server root account name",
        help="Enter the server root account name.",
        key=f"{id}-root",
    )
    pw = st.text_input(
        "Password",
        placeholder="Enter the server password",
        help="The password for the server.",
        type="password",
        key=f"{id}-pw",
    )
    return ip, port, root, pw


def setup(infra: Infrastructure, config: ServiceConfig) -> Dict:
    params = dict()

    ip, port, root, pw = form_add_server(f"{len(infra.bundles) + 1}-{config.id}")

    params["${MLOX_IP}"] = ip
    params["${MLOX_PORT}"] = str(port)
    params["${MLOX_ROOT}"] = root
    params["${MLOX_ROOT_PW}"] = pw

    return params


def settings(infra: Infrastructure, bundle: Bundle, server: UbuntuNativeServer):
    if server.mlox_user:
        if server.is_debug_access_enabled or "mlox.debug" in bundle.tags:
            st.markdown("Debug access is enabled.")
            st.markdown(
                "You can access the server via SSH using the following command:"
            )
            st.markdown(f"```bash\nssh {server.mlox_user.name}@{server.ip}\n```")
            st.markdown(f"Password: `{server.mlox_user.pw}`\n")
        # st.write(f"ssh {server.mlox_user.name}@{server.ip}")
        # st.write(server.mlox_user.pw)

    if server.state != "running":
        st.markdown("Server is not running. Please start the server first.")
        return

    tab_server, tab_backend = st.tabs(["Server Info", "Backend Status"])
    with tab_server:
        st.write(server.get_server_info())

    with tab_backend:
        st.write(server.get_backend_status())
