import streamlit as st

from mlox.services.redis.docker import RedisDockerService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: RedisDockerService):
    st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    st.write(f"user: redis")
    st.write(f'password: "{service.pw}"')
    st.write(f'port: "{service.port}"')

    st.write(f'url: "{service.service_urls["Redis"]}"')
