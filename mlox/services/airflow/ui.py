import pandas as pd
import streamlit as st

from typing import cast
from datetime import datetime

from mlox.services.utils_ui import save_infrastructure
from mlox.services.airflow.docker import AirflowDockerService
from mlox.services.github.service import GithubRepoService
from mlox.infra import Infrastructure, Bundle
from mlox.server import AbstractGitServer


def settings(infra: Infrastructure, bundle: Bundle, service: AirflowDockerService):
    tab_general, tab_repos = st.tabs(["General", "Repositories"])
    with tab_general:
        st.header(f"Settings for service {service.name}")
        st.write(f"IP: {bundle.server.ip}")
        st.write(f"UI User: {service.ui_user}")
        st.write(f'UI Password: "{service.ui_pw}"')
    with tab_repos:
        tab_repositories(infra, bundle, service)


def tab_repositories(
    infra: Infrastructure, bundle: Bundle, service: AirflowDockerService
):
    my_repos = []
    for r in infra.filter_by_group("git"):
        my_repos.append(
            {
                "name": r.name,
                "link": r.link,
                "path": r.target_path,
                "created": datetime.fromisoformat(r.created_timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "is_in_dags": r.target_path.startswith(service.path_dags),
                "repo": r,
            }
        )

    df = pd.DataFrame(
        my_repos,
        columns=["name", "link", "path", "created", "is_in_dags", "repo"],
    )

    # add a repository to the DAGs
    st.markdown(
        "#### Add or remove repositories from DAGs\n"
        "You can add or remove repositories from the DAGs folder. "
        "This will allow you to manage your Airflow DAGs more easily."
    )
    st.markdown("### Available repositories")
    selection = st.dataframe(
        df[df["is_in_dags"] == False][["name", "link", "path", "created"]],
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        repo = my_repos[idx]["repo"]
        if st.button("Add to DAGs"):
            new_repo = GithubRepoService(
                repo.repo_name + " [Airflow DAG]",
                repo.template,
                service.path_dags,
                repo.link,
            )
            config = infra.get_service_config(repo)
            if config:
                infra.add_service(bundle.server.ip, config, params={}, service=new_repo)
                with bundle.server.get_server_connection() as conn:
                    new_repo.setup(conn)
                    new_repo.spin_up(conn)
                    new_repo.create_and_add_repo(bundle)
                save_infrastructure()
                st.rerun()

    st.markdown("#### Associated repositories")
    selection = st.dataframe(
        df[df["is_in_dags"] == True][["name", "link", "path", "created"]],
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        repo = my_repos[idx]["repo"]
        if st.button("Remove from DAGs"):
            infra.teardown_service(repo)
            save_infrastructure()
            st.rerun()
