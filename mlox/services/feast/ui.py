import streamlit as st

from typing import Dict

from mlox.services.feast.docker import FeastDockerService
from mlox.infra import Infrastructure, Bundle

from mlox.services.utils_ui import save_to_secret_store


def setup(infra: Infrastructure, bundle: Bundle) -> Dict:
    params: Dict = dict()
    st.write("Feast")

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: FeastDockerService):
    st.write(f"host: {service.service_urls}")

    st.write(f"port: {service.port}")
    st.write(f"user: {service.user}, password: {service.pw}")

    # save_to_secret_store(
    #     infra,
    #     f"MLOX_FEAST_{service.name.upper()}",
    #     {
    #         "url": service.service_urls["Feast"],
    #         "user": service.user,
    #         "port": service.port,
    #         "password": service.pw,
    #         "certificate": service.certificate,
    #     },
    # )
