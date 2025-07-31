import streamlit as st

from typing import Dict, Any

from mlox.services.github.service import GithubRepoService
from mlox.infra import Infrastructure, Bundle
from mlox.view.utils import st_hack_align, save_infra


def setup(infra: Infrastructure, bundle: Bundle) -> Dict[str, Any] | None:
    params = None

    st.markdown("If you like to add ")

    c1, c2, c3 = st.columns([40, 40, 20])

    user_name = c1.text_input("User or Organization Name", value="")
    repo_name = c2.text_input("Repository Name", value="")

    st_hack_align(c3, px=32)
    is_private = c3.checkbox("Private Repository", value=False)

    # link = f"https://github.com/{user_name}/{repo_name}.git"
    link = f"git@github.com:{user_name}/{repo_name}.git"
    st.markdown(f"Link: {link}")

    if user_name and repo_name:
        params = {
            "${GITHUB_LINK}": link,
            "${GITHUB_NAME}": repo_name,
            "${GITHUB_PRIVATE}": str(is_private),
        }

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: GithubRepoService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")
    st.write(f'Link: "{service.link}"')
    st.write(f'Path: "{service.target_path}"')
    st.write(f'Private: "{service.private_repo}"')
    st.write(f'created_timestamp: "{service.created_timestamp}"')
    st.write(f'modified_timestamp: "{service.modified_timestamp}"')

    info = service.check(bundle.server.get_server_connection())
    st.write(info)

    if info.get("cloned", False):
        if st.button("Pull", type="primary"):
            with st.spinner("Pulling repo...", show_time=True):
                with bundle.server.get_server_connection() as conn:
                    service.git_pull(conn)
            save_infra()
            st.rerun()
    elif info.get("private", False):
        st.markdown(
            "Add the following deploy key to your GitHub repository Settings > Deploy Keys"
        )
        st.text_area("Deploy Key", service.deploy_key, height=200, disabled=True)
        if st.button("Clone", type="primary"):
            with st.spinner("Cloning repo...", show_time=True):
                with bundle.server.get_server_connection() as conn:
                    service.git_clone(conn)
            save_infra()
            st.rerun()

    if service.state == "unknown":
        st.info(
            "The service is in an unknown state. Please check the logs for more information."
        )
