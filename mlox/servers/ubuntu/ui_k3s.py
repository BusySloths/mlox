import streamlit as st

from typing import Dict

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure, Bundle
from mlox.servers.ubuntu.k3s import UbuntuK3sServer
from mlox.servers.ubuntu.ui_native import setup as setup_native


def setup(infra: Infrastructure, config: ServiceConfig) -> Dict:
    params = setup_native(infra, config)

    controller_url = ""
    controller_token = ""

    k8s_controller = [None] + infra.list_kubernetes_controller()
    join_k8s_bundle = st.selectbox(
        "Create new Kubernetes cluster or select existing controller to join",
        k8s_controller,
        format_func=lambda x: "Create new cluster" if not x else x.name,
    )

    if join_k8s_bundle:
        controller_url = f"https://{join_k8s_bundle.server.ip}:6443"
        controller_token = join_k8s_bundle.server.get_backend_status().get(
            "k3s.token", ""
        )

    params["${K3S_CONTROLLER_URL}"] = controller_url
    params["${K3S_CONTROLLER_TOKEN}"] = controller_token

    return params


def settings(infra: Infrastructure, bundle: Bundle, server: UbuntuK3sServer):
    st.markdown(f"#### {bundle.name}")
