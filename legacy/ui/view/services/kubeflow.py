import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.services.kubeflow.k8s import KubeflowService


def settings(
    infra: Infrastructure,  # noqa: ARG001
    bundle: Bundle,  # noqa: ARG001
    service: KubeflowService,
) -> None:
    service_url = service.service_urls.get("Kubeflow", "")
    port = service.service_ports.get("Kubeflow", service.ingress_port)

    st.link_button(
        "Open Kubeflow",
        url=service_url,
        icon=":material/open_in_new:",
    )
    st.write(f"HTTPS port: `{port}`")
    st.write("Initial Dex email")
    st.code(service.dex_email)
    st.write("Initial Dex password")
    st.code(service.dex_password)
    st.caption("Change the initial password after the first successful login.")
