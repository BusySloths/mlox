import streamlit as st

from mlox.services.redis.docker import RedisDockerService
from mlox.infra import Infrastructure, Bundle

from mlox.services.utils_ui import save_to_secret_store


def settings(infra: Infrastructure, bundle: Bundle, service: RedisDockerService):
    # st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    st.write(
        f"host: {service.service_urls['Redis IP']}, user: redis, password: {service.pw}, port: {service.port}"
    )

    save_to_secret_store(
        infra,
        f"MLOX_REDIS_{service.name.upper()}",
        {
            "url": service.service_urls["Redis"].rpartition(":")[0],
            "ip": service.service_urls["Redis IP"],
            "user": "redis",
            "port": service.port,
            "password": service.pw,
            "certificate": service.certificate,
        },
    )
