import logging
from datetime import datetime

import pytest

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

PUBLIC_MLOX_REPO = "https://github.com/busysloths/mlox.git"


@pytest.fixture(scope="module")
def github_repo_service(ubuntu_docker_server):
    """Provision the GitHub repository service pointing at the public mlox repo."""

    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/github", "mlox.github.yaml")
    if not config:
        pytest.skip("GitHub repository stack configuration could not be loaded")

    params = {
        "${GITHUB_LINK}": PUBLIC_MLOX_REPO,
        "${GITHUB_PRIVATE}": False,
    }

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params=params)
    if not bundle_added:
        pytest.skip("Failed to add GitHub repository service to the infrastructure")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.teardown(conn)
        except Exception as exc:  # pragma: no cover - teardown best effort
            logger.warning(
                "Ignoring error during GitHub repository service teardown: %s", exc
            )

    infra.remove_bundle(bundle_added)


def test_github_repo_public_clone(github_repo_service):
    """The public mlox repository should be cloned onto the remote host."""
    bundle, service = github_repo_service

    assert service.repo_name == "mlox"
    assert service.service_urls.get("Repository") == "https://github.com/busysloths/mlox"

    with bundle.server.get_server_connection() as conn:
        status = service.check(conn)

    assert service.cloned is True
    assert status.get("cloned") is True
    assert status.get("exists") is True
    assert status.get("private") is False
    assert "README.md" in status.get("files", [])


def test_github_repo_public_pull(github_repo_service):
    """Invoking git_pull should succeed and refresh the modified timestamp."""
    bundle, service = github_repo_service
    previous_modified = service.modified_timestamp

    with bundle.server.get_server_connection() as conn:
        service.git_pull(conn)
        status = service.check(conn)

    assert status.get("exists") is True
    assert status.get("cloned") is True
    assert service.cloned is True

    new_modified = datetime.fromisoformat(service.modified_timestamp)
    old_modified = datetime.fromisoformat(previous_modified)
    assert new_modified >= old_modified
