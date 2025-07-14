import streamlit as st

from mlox.services.redis.docker import RedisDockerService
from mlox.infra import Infrastructure, Bundle

from mlox.services.utils_ui import save_to_secret_store


def settings(infra: Infrastructure, bundle: Bundle, service: RedisDockerService):
    # st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    st.write(f"user: redis")
    st.write(f'password: "{service.pw}"')
    st.write(f'port: "{service.port}"')

    st.write(f'url: "{service.service_urls["Redis"]}"')

    save_to_secret_store(
        infra,
        f"MLOX_REDIS_{service.name.upper()}",
        {
            "url": service.service_urls["Redis"].rpartition(":")[0],
            "user": "redis",
            "port": service.port,
            "password": service.pw,
            "certificate": service.certificate,
        },
    )
