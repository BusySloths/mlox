from __future__ import annotations

import os
import pandas as pd
import streamlit as st

from typing import Any, Dict

from mlox.infra import Infrastructure, Bundle
from mlox.services.utils_ui import save_infrastructure
from mlox.services.repo_deploy.service import RepoDeployDockerService


def _repo_root(repo_service: Any) -> str:
    repo_name = getattr(repo_service, "repo_name", "")
    repo_target_path = getattr(repo_service, "target_path", "")
    return f"{repo_target_path}/{repo_name}" if repo_name else repo_target_path


def _find_compose_files(bundle: Bundle, repo_service: Any) -> list[str]:
    repo_root = _repo_root(repo_service)
    if not repo_root:
        return []
    with bundle.server.get_server_connection() as conn:
        tree = repo_service.exec.fs_list_file_tree(conn, repo_root)
    repo_root_prefix = repo_root.rstrip("/") + "/"
    files: list[str] = []
    for entry in tree:
        if not entry.get("is_file", False):
            continue
        path = str(entry.get("path", ""))
        basename = os.path.basename(path).lower()
        if "compose" not in basename:
            continue
        if not basename.endswith(('.yaml', '.yml')):
            continue
        if path.startswith(repo_root_prefix):
            files.append(path[len(repo_root_prefix) :])
        else:
            files.append(path)
    return sorted(set(files))


def setup(infra: Infrastructure, bundle: Bundle) -> Dict[str, Any] | None:
<<<<<<< ours
<<<<<<< ours
    repos = [
        repo
        for repo in infra.filter_by_group("repository")
        if infra.get_bundle_by_service(repo) == bundle
    ]

    if not repos:
        st.info(
            "No repository services are available on this server. Install a GitHub repository service first."
=======
=======
>>>>>>> theirs
    docker_bundles = infra.filter_bundles_by_backend("docker")
    repos = []
    repo_to_bundle: dict[str, Bundle] = {}
    for repo in infra.filter_by_group("repository"):
        repo_bundle = infra.get_bundle_by_service(repo)
        if not repo_bundle or repo_bundle not in docker_bundles:
            continue
        repos.append(repo)
        repo_to_bundle[repo.uuid] = repo_bundle

    if not repos:
        st.info(
            "No repository services are available on docker servers. Install a GitHub repository service first."
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
        )
        return None

    selected_repo = st.selectbox(
        "Repository service",
        options=repos,
<<<<<<< ours
<<<<<<< ours
        format_func=lambda repo: f"{repo.name} ({repo.uuid[:8]})",
        key="repo-deploy-select-repo",
    )

    compose_files = _find_compose_files(bundle, selected_repo)
    if not compose_files:
        st.warning("No docker compose files found in the selected repository.")

=======
=======
>>>>>>> theirs
        format_func=lambda repo: (
            f"{repo.name} ({repo.uuid[:8]}) "
            f"@ {repo_to_bundle[repo.uuid].name} ({repo_to_bundle[repo.uuid].server.ip})"
        ),
        key="repo-deploy-select-repo",
    )
    selected_repo_bundle = repo_to_bundle[selected_repo.uuid]

    compose_files = _find_compose_files(selected_repo_bundle, selected_repo)
    if not compose_files:
        st.warning("No docker compose files found in the selected repository.")

    if selected_repo_bundle != bundle:
        st.info(
            "This deployment will be installed automatically on the repository server: "
            f"`{selected_repo_bundle.server.ip}`."
        )

<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
    compose_file = st.selectbox(
        "Compose file",
        options=compose_files,
        index=None,
        placeholder="Select a compose file",
        key="repo-deploy-select-compose-file",
    )

    target_suffix = st.text_input(
        "Deployment folder name",
        value=f"repo-deploy-{getattr(selected_repo, 'repo_name', 'service')}",
    )

    if not compose_file:
        return None

    return {
        "${REPO_DEPLOY_NAME}": target_suffix,
        "${REPO_DEPLOY_REPO_UUID}": selected_repo.uuid,
        "${REPO_DEPLOY_COMPOSE_FILE}": compose_file,
<<<<<<< ours
<<<<<<< ours
=======
        "__MLOX_TARGET_SERVER_IP": selected_repo_bundle.server.ip,
>>>>>>> theirs
=======
        "__MLOX_TARGET_SERVER_IP": selected_repo_bundle.server.ip,
>>>>>>> theirs
    }


def settings(infra: Infrastructure, bundle: Bundle, service: RepoDeployDockerService):
    st.markdown(f"Repository UUID: `{service.repo_uuid}`")
    st.markdown(f"Compose file: `{service.compose_file}`")

    if service.service_ports:
        st.markdown("#### Discovered ports")
        st.dataframe(
            pd.DataFrame(
                [
                    {"endpoint": label, "port": port}
                    for label, port in service.service_ports.items()
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )

    st.markdown("#### Environment variables (.env)")
    env_rows = [
        {"key": key, "value": value}
        for key, value in sorted((service.env_vars or {}).items())
    ]
    edited_df = st.data_editor(
        pd.DataFrame(env_rows or [{"key": "", "value": ""}]),
        num_rows="dynamic",
        use_container_width=True,
        key=f"repo-deploy-env-editor-{service.uuid}",
        column_config={
            "key": st.column_config.TextColumn("Key", required=True),
            "value": st.column_config.TextColumn("Value"),
        },
        hide_index=True,
    )

    if st.button("Save .env", type="primary", key=f"repo-deploy-save-env-{service.uuid}"):
        rows = edited_df.to_dict("records")
        new_env = {
            str(row.get("key", "")).strip(): str(row.get("value", ""))
            for row in rows
            if str(row.get("key", "")).strip()
        }
        with bundle.server.get_server_connection() as conn:
            service.save_env_vars(conn, new_env)
        save_infrastructure()
        st.success("Updated environment file.")
        st.rerun()
<<<<<<< ours
<<<<<<< ours
=======
=======
>>>>>>> theirs

    st.markdown("#### Update from repository")
    col_service, col_btn = st.columns([3, 1])
    compose_service = col_service.text_input(
        "Compose service name",
        value="app",
        help="Service name passed to `docker compose up --build -d <service>`.",
        key=f"repo-deploy-update-service-{service.uuid}",
    )
    if col_btn.button("Update", type="secondary", key=f"repo-deploy-update-{service.uuid}"):
        with st.spinner("Pulling latest git changes and redeploying...", show_time=True):
            with bundle.server.get_server_connection() as conn:
                service.update_and_redeploy(conn, compose_service=compose_service.strip())
            save_infrastructure()
        st.success("Updated repository and redeployed service.")
        st.rerun()
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
