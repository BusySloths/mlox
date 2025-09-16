import logging
from datetime import datetime

import pytest

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from mlox.remote import exec_command, fs_create_dir, fs_write_file

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

PUBLIC_MLOX_REPO = "https://github.com/busysloths/mlox.git"
PRIVATE_MLOX_REPO = "git@github.com:busysloths/mlox-test-private-repo.git"
PRIVATE_MLOX_REPO_HTTP_URL = "https://github.com/busysloths/mlox-test-private-repo"
# Path to the private key file; public key is expected at "<path>.pub"
PRIVATE_DEPLOY_KEY_FILE = "mlox_integration_tests_key"


def _normalize_key_material(key_material: str) -> str:
    normalized = key_material.strip()
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _install_preconfigured_deploy_keys(
    conn, server, service, public_key: str, private_key: str
) -> None:
    key_name = f"mlox_deploy_{service.repo_name}"
    ssh_dir = f"{service.target_path}/.ssh"
    fs_create_dir(conn, ssh_dir)
    exec_command(conn, f"chmod 700 {ssh_dir}")

    private_key_path = f"{ssh_dir}/{key_name}"
    public_key_path = f"{private_key_path}.pub"

    fs_write_file(conn, private_key_path, _normalize_key_material(private_key))
    exec_command(conn, f"chmod 600 {private_key_path}")
    fs_write_file(conn, public_key_path, _normalize_key_material(public_key))
    exec_command(conn, f"chmod 644 {public_key_path}")
    service.deploy_key = public_key.strip()

    home_dir = getattr(server.mlox_user, "home", None)
    if home_dir:
        home_ssh_dir = f"{home_dir}/.ssh"
    else:
        home_ssh_dir = "~/.ssh"
    fs_create_dir(conn, home_ssh_dir)
    exec_command(conn, f"chmod 700 {home_ssh_dir}")
    exec_command(
        conn,
        f"ssh-keyscan -t rsa github.com >> {home_ssh_dir}/known_hosts",
        sudo=False,
    )


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
    assert (
        service.service_urls.get("Repository") == "https://github.com/busysloths/mlox"
    )

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


@pytest.fixture(scope="module")
def github_private_repo_service(ubuntu_docker_server):
    """Provision the GitHub repository service for a private repository."""

    public_key_path = f"{PRIVATE_DEPLOY_KEY_FILE}.pub"
    private_key_path = f"{PRIVATE_DEPLOY_KEY_FILE}"
    try:
        with open(private_key_path, "r") as f:
            private_key = f.read()
        with open(public_key_path, "r") as f:
            public_key = f.read()
    except FileNotFoundError:
        pytest.skip(
            f"Deploy key files not found: '{private_key_path}' and/or '{public_key_path}'"
        )

    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/github", "mlox.github.yaml")
    if not config:
        pytest.skip("GitHub repository stack configuration could not be loaded")

    params = {
        "${GITHUB_LINK}": PRIVATE_MLOX_REPO,
        "${GITHUB_PRIVATE}": True,
    }

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params=params)
    if not bundle_added:
        pytest.skip(
            "Failed to add private GitHub repository service to the infrastructure"
        )

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        _install_preconfigured_deploy_keys(
            conn, bundle_added.server, service, public_key, private_key
        )
        service.git_clone(conn)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.teardown(conn)
        except Exception as exc:  # pragma: no cover - teardown best effort
            logger.warning(
                "Ignoring error during private GitHub repository service teardown: %s",
                exc,
            )

    infra.remove_bundle(bundle_added)


def test_github_repo_private_clone(github_private_repo_service):
    """The private repository should clone successfully using the provided deploy key."""

    bundle, service = github_private_repo_service

    assert service.repo_name == "mlox-test-private-repo"
    assert service.service_urls.get("Repository") == PRIVATE_MLOX_REPO_HTTP_URL
    public_key_path = f"{PRIVATE_DEPLOY_KEY_FILE}.pub"
    private_key_path = f"{PRIVATE_DEPLOY_KEY_FILE}"
    if private_key_path:
        public_key_path = f"{private_key_path}.pub"
        try:
            with open(public_key_path, "r") as f:
                expected_public_key = f.read()
            assert service.deploy_key.strip() == expected_public_key.strip()
        except FileNotFoundError:
            pass

    with bundle.server.get_server_connection() as conn:
        status = service.check(conn)

    assert service.cloned is True
    assert status.get("cloned") is True
    assert status.get("exists") is True
    assert status.get("private") is True
    assert ".git" in status.get("files", [])


def test_github_repo_private_pull(github_private_repo_service):
    """Running git_pull for the private repository should update its modified timestamp."""

    bundle, service = github_private_repo_service
    previous_modified = service.modified_timestamp

    with bundle.server.get_server_connection() as conn:
        service.git_pull(conn)
        status = service.check(conn)

    assert status.get("exists") is True
    assert status.get("cloned") is True
    assert service.cloned is True
    assert status.get("private") is True

    new_modified = datetime.fromisoformat(service.modified_timestamp)
    old_modified = datetime.fromisoformat(previous_modified)
    assert new_modified >= old_modified
