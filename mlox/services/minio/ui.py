import streamlit as st

from mlox.infra import Infrastructure, Bundle
from mlox.services.minio.docker import MinioDockerService
from mlox.services.utils_ui import save_to_secret_store


def settings(infra: Infrastructure, bundle: Bundle, service: MinioDockerService):
    st.write(f"Endpoint: {service.service_url}")
    st.write(f"Console: {service.console_url}")
    st.write(f"Root user: {service.root_user}")
    st.write(f'Root password: "{service.root_password}"')

    save_to_secret_store(
        infra,
        f"MLOX_MINIO_{service.name.upper()}",
        {
            "api_url": service.service_url,
            "console_url": service.console_url,
            "access_key": service.root_user,
            "secret_key": service.root_password,
        },
    )

    st.link_button(
        "Open MinIO Console",
        url=service.console_url,
        icon=":material/open_in_new:",
        help="Open the MinIO web console",
    )

    st.code(
        f"""
import boto3

s3 = boto3.resource(
    "s3",
    endpoint_url="{service.service_url}",
    aws_access_key_id="{service.root_user}",
    aws_secret_access_key="{service.root_password}",
    verify=False,
)
        """.strip(),
        language="python",
        line_numbers=True,
    )

    if service.certificate:
        st.markdown("#### TLS certificate")
        st.code(service.certificate.strip(), language="bash")
