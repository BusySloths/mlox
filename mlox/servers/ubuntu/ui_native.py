import streamlit as st

from typing import Dict

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure, Bundle
from mlox.servers.ubuntu.native import UbuntuNativeServer


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
    return ip, port, root, pw


def setup(infra: Infrastructure, config: ServiceConfig) -> Dict:
    params = dict()

    ip, port, root, pw = form_add_server()

    params["${MLOX_IP}"] = ip
    params["${MLOX_PORT}"] = str(port)
    params["${MLOX_ROOT}"] = root
    params["${MLOX_ROOT_PW}"] = pw

    return params


def settings(infra: Infrastructure, bundle: Bundle, server: UbuntuNativeServer):
    st.markdown(f"#### {bundle.name}")
