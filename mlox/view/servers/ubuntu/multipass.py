from __future__ import annotations

import uuid

import streamlit as st

from typing import Dict

from mlox.config import ServiceConfig
from mlox.infra import Bundle, Infrastructure
from mlox.servers.ubuntu.multipass import MultipassUbuntuServerMixin
from mlox.view.servers.ubuntu.native import settings as settings_native


def _multipass_form(sid: str) -> Dict[str, str]:
    form_id = f"form-add-multipass-server-{sid}"
    st.caption(
        "Launch a local Ubuntu VM with Multipass. Root SSH is bootstrapped with "
        "the built-in cloud-init file and then MLOX provisions the selected backend."
    )
    vm_name = st.text_input(
        "VM name",
        value=f"mlox-{uuid.uuid4().hex[:8]}",
        help="Unique Multipass instance name.",
        key=f"{form_id}-vm-name",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        cpus = st.number_input(
            "CPUs",
            value=2,
            min_value=1,
            max_value=32,
            step=1,
            help="Number of virtual CPUs for the Multipass VM.",
            key=f"{form_id}-cpus",
        )
    with c2:
        memory = st.text_input(
            "RAM",
            value="4G",
            help="Memory passed to Multipass, for example 4G or 8192M.",
            key=f"{form_id}-memory",
        )
    with c3:
        disk = st.text_input(
            "Disk",
            value="20G",
            help="Disk size passed to Multipass, for example 20G.",
            key=f"{form_id}-disk",
        )
    image = st.text_input(
        "Ubuntu image",
        value="24.04",
        help="Multipass image/alias to launch.",
        key=f"{form_id}-image",
    )
    cloud_init = st.text_input(
        "Cloud-init path (optional)",
        value="",
        help="Leave empty to use the bundled MLOX Multipass cloud-init file.",
        key=f"{form_id}-cloud-init",
    )
    launch_timeout = st.number_input(
        "Launch timeout (seconds)",
        value=600,
        min_value=60,
        max_value=1800,
        step=60,
        help="Maximum time to wait for SSH login on first boot.",
        key=f"{form_id}-launch-timeout",
    )
    return {
        "${MULTIPASS_VM_NAME}": vm_name,
        "${MULTIPASS_CPUS}": str(cpus),
        "${MULTIPASS_MEMORY}": memory,
        "${MULTIPASS_DISK}": disk,
        "${MULTIPASS_IMAGE}": image,
        "${MULTIPASS_CLOUD_INIT}": cloud_init,
        "${MULTIPASS_LAUNCH_TIMEOUT}": str(launch_timeout),
    }


def setup(infra: Infrastructure, config: ServiceConfig) -> Dict:
    return _multipass_form(f"{len(infra.bundles) + 1}-{config.id}")


def setup_k3s_multipass(infra: Infrastructure, config: ServiceConfig) -> Dict:
    params = _multipass_form(f"{len(infra.bundles) + 1}-{config.id}")
    controller_url = ""
    controller_token = ""
    controller_uuid = ""

    k8s_controller = [None] + infra.list_kubernetes_controller()
    join_k8s_bundle = st.selectbox(
        "Create new Kubernetes cluster or select existing controller to join",
        k8s_controller,
        format_func=lambda x: "Create new cluster" if not x else x.name,
        key=f"setup-k3s-multipass-controller-{config.id}",
    )

    if join_k8s_bundle:
        controller_url = f"https://{join_k8s_bundle.server.ip}:6443"
        controller_token = join_k8s_bundle.server.get_backend_status().get(
            "k3s.token", ""
        )
        controller_uuid = join_k8s_bundle.server.uuid

    params["${K3S_CONTROLLER_URL}"] = controller_url
    params["${K3S_CONTROLLER_TOKEN}"] = controller_token
    params["${K3S_CONTROLLER_UUID}"] = controller_uuid
    return params


def settings(infra: Infrastructure, bundle: Bundle, server: MultipassUbuntuServerMixin):
    with st.expander("Multipass VM", expanded=False):
        st.json(
            {
                "vm_name": server.vm_name,
                "ip": server.ip,
                "state": server.state,
                "cpus": server.cpus,
                "memory": server.memory,
                "disk": server.disk,
                "image": server.image,
            }
        )
    settings_native(infra, bundle, server)  # type: ignore[arg-type]
