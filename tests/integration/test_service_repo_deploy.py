from tests.integration.helpers import add_service
import logging

import pytest

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

PUBLIC_MLOX_REPO = "https://github.com/busysloths/mlox.git"


@pytest.fixture(scope="module")
def install_repo_deploy_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    github_config = load_config(get_stacks_path(), "/github", "mlox.github.yaml")
    if not github_config:
        pytest.skip("GitHub repository stack configuration could not be loaded")

    github_params = {
        "${GITHUB_LINK}": PUBLIC_MLOX_REPO,
        "${GITHUB_PRIVATE}": False,
    }
    bundle_added = add_service(
        infra,
        ubuntu_docker_server.ip,
        github_config,
        params=github_params,
    )
    if not bundle_added:
        pytest.skip("Failed to add GitHub repository service")

    repo_service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        repo_service.setup(conn)

    deploy_config = load_config(
        get_stacks_path(),
        "/repo_deploy",
        "mlox.repo_deploy.0.1.yaml",
    )
    if not deploy_config:
        pytest.skip("Repo deploy service configuration could not be loaded")

    deploy_params = {
        "${REPO_DEPLOY_NAME}": "integration-repo-deploy",
        "${REPO_DEPLOY_REPO_UUID}": repo_service.uuid,
        "${REPO_DEPLOY_COMPOSE_FILE}": "mlox/services/redis/docker-compose-redis-8-bookworm.yaml",
    }
    bundle_added = add_service(
        infra,
        ubuntu_docker_server.ip,
        deploy_config,
        params=deploy_params,
    )
    if not bundle_added:
        pytest.skip("Failed to add Repo deploy service")

    deploy_service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        deploy_service.setup(conn)

    yield bundle_added, repo_service, deploy_service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            deploy_service.teardown(conn)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Ignoring error during repo deploy teardown: %s", exc)
        try:
            repo_service.teardown(conn)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Ignoring error during github repo teardown: %s", exc)

    infra.remove_bundle(bundle_added)


def test_repo_deploy_setup_creates_compose_and_env(install_repo_deploy_service):
    bundle, _, deploy_service = install_repo_deploy_service

    assert deploy_service.compose_service_names == {"redis": "redis"}
    assert deploy_service.service_ports.get("redis:1") is not None
    assert deploy_service.env_vars.get("MY_REDIS_PORT", "") == ""
    assert deploy_service.env_vars.get("MY_REDIS_PW", "") == ""

    with bundle.server.get_server_connection() as conn:
        compose_data = deploy_service.exec.fs_read_file(
            conn,
            f"{deploy_service.target_path}/{deploy_service.target_docker_script}",
            format="yaml",
        )
        env_content = deploy_service.exec.fs_read_file(
            conn,
            f"{deploy_service.target_path}/{deploy_service.target_docker_env}",
            format="string",
        )

    assert isinstance(compose_data, dict)
    assert "services" in compose_data
    assert "MY_REDIS_PORT=" in env_content
    assert "MY_REDIS_PW=" in env_content
