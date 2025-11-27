import logging
import pandas as pd
import streamlit as st

from typing import cast
from datetime import datetime

from mlox.services.utils_ui import save_infrastructure
from mlox.services.airflow.docker import AirflowDockerService
from mlox.services.github.service import GithubRepoService
from mlox.infra import Infrastructure, Bundle, Repo
from mlox.server import AbstractGitServer
from mlox.service import AbstractService

logger = logging.getLogger(__name__)


def settings(infra: Infrastructure, bundle: Bundle, service: AirflowDockerService):
    st.link_button(
        "Open Airflow UI",
        url=service.service_urls["Airflow UI"],
        icon=":material/open_in_new:",
        help="Open the Airflow UI in a new tab",
    )

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
    for r in infra.filter_by_group("repository"):
        # if not isinstance(r, GithubRepoService):
        #     continue
        t = (
            r.created_timestamp
            if hasattr(r, "created_timestamp")
            else "2001-01-01T00:00:00"
        )
        my_repos.append(
            {
                "name": r.name,
                "link": r.link if hasattr(r, "link") else "",
                "path": r.target_path,
                "created": datetime.fromisoformat(t).strftime("%Y-%m-%d %H:%M:%S"),
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
        key="airflow-repo-select",
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        repo = cast(GithubRepoService, my_repos[idx]["repo"])
        repo_service = cast(AbstractService, my_repos[idx]["repo"])
        if st.button("Add to DAGs"):
            new_repo = GithubRepoService(
                name=repo.repo_name + " [Airflow DAG]",
                is_private=repo.is_private,
                service_config_id=repo_service.service_config_id,
                template=repo_service.template,
                target_path=service.path_dags,
                link=repo.link,
            )
            config = infra.get_service_config(repo_service)
            if config:
                infra.add_service(bundle.server.ip, config, params={}, service=new_repo)
                with bundle.server.get_server_connection() as conn:
                    new_repo.setup(conn)
                    new_repo.spin_up(conn)
                    try:
                        new_repo.git_clone(conn)
                        new_repo.git_pull(conn)
                    except Exception as e:
                        logger.info(
                            f"Error cloning or pulling repository (repo exists already)): {e}"
                        )
                save_infrastructure()
                st.rerun()

    st.markdown("#### Associated repositories")
    selection = st.dataframe(
        df[df["is_in_dags"] == True][["name", "link", "path", "created"]],
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
        key="airflow-repo-associated",
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        repo_service = cast(AbstractService, my_repos[idx]["repo"])
        if st.button("Remove from DAGs"):
            st.error("Removing repositories from Airflow DAGs is not yet supported.")
            # infra.teardown_service(repo_service)
            # save_infrastructure()
            # st.rerun()
