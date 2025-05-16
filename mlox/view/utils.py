import streamlit as st

from mlox.infra import Infrastructure
from mlox.server import Ubuntu
from mlox.config import load_all_server_configs


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
    help_text = "Please select the configuration that matches your VPS system."
    configs = load_all_server_configs("./stacks")
    config = st.selectbox(
        "System Configuration",
        configs,
        format_func=lambda x: f"{x.name} {x.versions}",
        help=help_text,
    )
    # st.write(config)
    return ip, port, root, pw, config
