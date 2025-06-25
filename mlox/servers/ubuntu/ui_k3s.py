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


# def setup(
#     self,
#     controller: Any | None = None,
# ) -> None:
#     if backend == "docker":
#         self.server.setup_docker()
#         self.server.start_docker_runtime()
#     elif backend == "kubernetes":
#         self.server.setup_kubernetes()
#         self.server.start_kubernetes_runtime()
#     elif backend == "kubernetes-agent" and controller:
#         stats = controller.server.get_kubernetes_status()
#         if "k3s.token" not in stats:
#             logging.error(
#                 "Token is missing in controller stats ip: %s", controller.server.ip
#             )
#             return
#         url = f"https://{controller.server.ip}:6443"
#         token = stats["k3s.token"]
#         self.server.setup_kubernetes(controller_url=url, controller_token=token)
#         self.server.start_kubernetes_runtime()
#         cluster_name = f"k8s-{controller.name}"
#         self.tags.append(cluster_name)
#         if cluster_name not in controller.tags:
#             controller.tags.append(cluster_name)
#     self.status = backend


def settings(infra: Infrastructure, bundle: Bundle, server: UbuntuK3sServer):
    st.header(f"Settings for server {server.ip}")
