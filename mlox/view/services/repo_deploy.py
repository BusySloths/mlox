from __future__ import annotations

import os
import pandas as pd
import streamlit as st

from typing import Any, Dict

from mlox.infra import Infrastructure, Bundle
from mlox.view.services.common import save_infrastructure
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


def _env_vars_to_text(env_vars: Dict[str, str] | None) -> str:
    return "\n".join(
        f"{key}={value}" for key, value in sorted((env_vars or {}).items())
    )


def _parse_env_text(env_text: str) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    for line in env_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].lstrip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            env_vars[key] = value
    return env_vars


def _read_env_text(
    bundle: Bundle, service: RepoDeployDockerService
) -> tuple[str, str, str | None]:
    fallback = _env_vars_to_text(service.env_vars)
    env_path = ""
    try:
        with bundle.server.get_server_connection() as conn:
            service._use_repo_runtime_paths()
            env_path = f"{service.target_path}/{service.target_docker_env}"
            content = service.exec.fs_read_file(
                conn,
                env_path,
                format="string",
            )
            if isinstance(content, str):
                return content.rstrip("\n"), env_path, None
    except Exception as exc:
        return fallback, env_path or service.target_docker_env, str(exc)
    return fallback, env_path or service.target_docker_env, None


def setup(infra: Infrastructure, bundle: Bundle) -> Dict[str, Any] | None:
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
        )
        return None

    selected_repo = st.selectbox(
        "Repository service",
        options=repos,
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

    compose_file = st.selectbox(
        "Compose file",
        options=compose_files,
        index=None,
        placeholder="Select a compose file",
        key="repo-deploy-select-compose-file",
    )

    target_suffix = st.text_input(
        "Deployment name",
        value=f"repo-deploy-{getattr(selected_repo, 'repo_name', 'service')}",
    )

    if not compose_file:
        return None

    return {
        "${REPO_DEPLOY_NAME}": target_suffix,
        "${REPO_DEPLOY_REPO_UUID}": selected_repo.uuid,
        "${REPO_DEPLOY_COMPOSE_FILE}": compose_file,
        "__MLOX_TARGET_SERVER_IP": selected_repo_bundle.server.ip,
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
            width="stretch",
        )

    st.markdown("#### Environment variables (.env)")
    env_text_default, env_path, env_read_error = _read_env_text(bundle, service)
    env_editor_key = f"repo-deploy-env-text-{service.uuid}"
    if env_editor_key not in st.session_state:
        st.session_state[env_editor_key] = env_text_default

    if env_read_error:
        st.warning(f"Could not read `{env_path}`. Showing saved environment values.")

    col_reload, _ = st.columns([1, 4])
    if col_reload.button(
        "Reload .env",
        type="secondary",
        key=f"repo-deploy-reload-env-{service.uuid}",
    ):
        st.session_state[env_editor_key] = env_text_default
        st.rerun()

    env_text = st.text_area(
        ".env",
        height=240,
        key=env_editor_key,
    )

    if st.button("Save .env", type="primary", key=f"repo-deploy-save-env-{service.uuid}"):
        new_env = _parse_env_text(env_text)
        with bundle.server.get_server_connection() as conn:
            service.save_env_text(conn, env_text, new_env)
        save_infrastructure()
        st.success("Updated environment file.")
        st.rerun()

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
