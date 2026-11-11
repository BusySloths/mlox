import streamlit as st

from typing import Dict

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure, Bundle
from mlox.servers.ubuntu.simple import UbuntuSimpleServer


def form_add_server():
    c1, c2 = st.columns(2)
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
    user = c1.text_input(
        "Account Name",
        value="root",
        placeholder="Enter the server account name",
        help="Account with existing access to the server.",
    )
    pw = c2.text_input(
        "Account Password",
        value="",
        placeholder="Enter the server password (optional)",
        help="Password for the account, if required.",
        type="password",
    )
    private_key = c1.text_area(
        "Private Key",
        placeholder="Paste the SSH private key (optional)",
        help="Private key for SSH authentication.",
    )
    passphrase = c2.text_input(
        "Private Key Passphrase",
        value="",
        placeholder="Enter passphrase if the key is encrypted",
        help="Passphrase protecting the private key (optional).",
        type="password",
    )
    return ip, port, user, pw, private_key, passphrase


def setup(infra: Infrastructure, config: ServiceConfig) -> Dict:
    params = dict()

    ip, port, user, pw, private_key, passphrase = form_add_server()

    params["${MLOX_IP}"] = ip
    params["${MLOX_PORT}"] = str(port)
    params["${MLOX_ROOT}"] = user
    params["${MLOX_ROOT_PW}"] = pw
    params["${MLOX_ROOT_PRIVATE_KEY}"] = private_key
    params["${MLOX_ROOT_PASSPHRASE}"] = passphrase

    return params


def settings(infra: Infrastructure, bundle: Bundle, server: UbuntuSimpleServer):
    if server.state != "running":
        st.markdown("Server is not running. Please start the server first.")
        return

    tab_server, tab_backend = st.tabs(["Server Info", "Backend Status"])
    with tab_server:
        st.write(server.get_server_info())

    with tab_backend:
        st.write(server.get_backend_status())
