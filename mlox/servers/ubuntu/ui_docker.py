import streamlit as st

from typing import Dict

from mlox.infra import Infrastructure, Bundle
from mlox.config import ServiceConfig
from mlox.servers.ubuntu.docker import UbuntuDockerServer
from mlox.servers.ubuntu.ui_native import setup as setup_native
from mlox.servers.ubuntu.ui_native import settings as settings_native


def setup(infra: Infrastructure, config: ServiceConfig) -> Dict:
    return setup_native(infra, config)


def settings(infra: Infrastructure, bundle: Bundle, server: UbuntuDockerServer):
    settings_native(infra, bundle, server)
    # st.markdown(f"#### {bundle.name}")

    # if server.mlox_user:
    #     st.write(f"ssh {server.mlox_user.name}@{server.ip}")
    #     st.write(server.mlox_user.pw)
