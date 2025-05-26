import streamlit as st


from mlox.services.otel.docker import OtelDockerService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: OtelDockerService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")

    # st.write(service.certificate)
