import streamlit as st

from mlox.services.influx.docker import InfluxDockerService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: InfluxDockerService):
    st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    st.write(f"user: {service.user}")
    st.write(f'password: "{service.pw}"')
    st.write(f'token: "{service.token}"')
