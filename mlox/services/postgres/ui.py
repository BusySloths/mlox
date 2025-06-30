import streamlit as st

from mlox.services.postgres.docker import PostgresDockerService
from mlox.infra import Infrastructure, Bundle


def setup(infra: Infrastructure, bundle: Bundle):
    params = dict()

    database_name = st.text_input("Database Name", value="mlox")
    params["${POSTGRES_DB}"] = database_name
    return params


def settings(infra: Infrastructure, bundle: Bundle, service: PostgresDockerService):
    st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    st.write(f"user: {service.user}")
    st.write(f'password: "{service.pw}"')
    st.write(f'database: "{service.db}"')
    st.write(f'port: "{service.port}"')

    st.write(f'url: "{service.service_urls["Postgres"]}"')
