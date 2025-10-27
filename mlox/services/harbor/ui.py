import streamlit as st

from mlox.infra import Infrastructure, Bundle
from mlox.services.harbor.docker import HarborDockerService
from mlox.services.utils_ui import save_to_secret_store


def settings(infra: Infrastructure, bundle: Bundle, service: HarborDockerService) -> None:
    st.write(f"Harbor UI: {service.service_url}")
    st.write(f"Container registry endpoint: {service.registry_url}")
    st.write(f"Administrator: {service.admin_username}")

    save_to_secret_store(
        infra,
        f"MLOX_HARBOR_{service.name.upper()}",
        {
            "ui_url": service.service_url,
            "registry_url": service.registry_url,
            "username": service.admin_username,
            "password": service.admin_password,
        },
    )

    st.link_button(
        "Open Harbor UI",
        url=service.service_url,
        icon=":material/open_in_new:",
        help="Open the Harbor web console",
    )

    st.code(
        f"""
docker login {service.registry_url} \
  --username {service.admin_username} \
  --password {service.admin_password}
        """.strip(),
        language="bash",
        line_numbers=True,
    )

    if service.certificate:
        st.markdown("#### TLS certificate")
        st.code(service.certificate.strip(), language="pem")
