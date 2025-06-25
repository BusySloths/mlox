import streamlit as st

from typing import Dict, Any

from mlox.services.github.service import GithubRepoService
from mlox.infra import Infrastructure, Bundle


def setup(infra: Infrastructure, bundle: Bundle) -> Dict[str, Any]:
    params = dict()

    link = st.text_input("Link", value="")

    params["${GITHUB_LINK}"] = link
    params["${SERVER_NAME}"] = bundle.name
    return params


def settings(infra: Infrastructure, bundle: Bundle, service: GithubRepoService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")
    st.write(f'Link: "{service.link}"')
    st.write(f'Path: "{service.target_path}"')
    st.write(f'created_timestamp: "{service.created_timestamp}"')
    st.write(f'modified_timestamp: "{service.modified_timestamp}"')

    if st.button("Pull Repo", type="primary"):
        service.pull_repo(bundle)

    if st.button("Create Repo", type="primary"):
        service.create_and_add_repo(bundle)
