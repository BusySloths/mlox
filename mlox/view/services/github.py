import pandas as pd
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

    if is_private:
        link = f"git@github.com:{user_name}/{repo_name}.git"
    else:
        link = f"https://github.com/{user_name}/{repo_name}.git"
    st.markdown(f"Link: {link}")

    if user_name and repo_name:
        params = {
            "${GITHUB_LINK}": link,
            "${GITHUB_NAME}": repo_name,
            "${GITHUB_PRIVATE}": is_private,
        }

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: GithubRepoService):
    # st.header(f"Settings for service {service.name}")
    # st.write(f'Link: "{service.link}"')
    # st.write(f'Path: "{service.target_path}"')
    st.write(service.target_path)
    with bundle.server.get_server_connection() as conn:
        info = service.check(conn)

    private_str = "**private**" if service.is_private else "**public**"
    st.markdown(f""" The {private_str} repository is accessible on `{bundle.name}`. It was created on `{service.created_timestamp}`
                and last modified on `{service.modified_timestamp}`.
            **Link:** [{service.get_url()}]({service.get_url()})
""")

    if info.get("cloned", False):
        if st.button("Pull", type="primary", key=f"service-github-pull-{service.name}"):
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

    if "tree" in info and len(info["tree"]) > 0:
        tree_df = pd.DataFrame(info["tree"])
        tree_df["path"] = tree_df["path"].str.removeprefix(
            service.target_path + "/" + service.repo_name
        )
        tree_df = tree_df[~tree_df["path"].str.startswith("/.git/")]

        show_path = st.text_input(
            "Filter Path", value="/", key=f"service-github-filter-path-{service.name}"
        )
        st.dataframe(
            tree_df[tree_df["path"].str.startswith(show_path)], hide_index=True
        )

    if service.state == "unknown":
        st.info(
            "The service is in an unknown state. Please check the logs for more information."
        )
