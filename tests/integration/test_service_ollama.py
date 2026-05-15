"""Integration tests for standalone Ollama service."""

import logging

import pytest
import requests

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from tests.integration.conftest import wait_for_service_ready

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]


@pytest.fixture(scope="module")
def install_ollama_service(ubuntu_docker_server):
    """Install and start the standalone Ollama service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/ollama", "mlox.ollama.0.23.3.yaml")
    params = {"${OLLAMA_MODELS}": []}

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params=params)
    if not bundle_added:
        pytest.skip("Failed to add Ollama service from config")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle_added, retries=6, interval=10, no_checks=True)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception as exc:
            logger.warning("Ignoring error during Ollama spin_down: %s", exc)
        try:
            service.teardown(conn)
        except Exception as exc:
            logger.warning("Ignoring error during Ollama teardown: %s", exc)
    infra.remove_bundle(bundle_added)


def test_ollama_service_is_running(install_ollama_service):
    bundle, service = install_ollama_service
    status = wait_for_service_ready(service, bundle, retries=30, interval=10)
    assert status.get("status") == "running"


def test_ollama_tags_requires_auth_and_works_with_auth(install_ollama_service):
    _, service = install_ollama_service
    host = service.service_url.split("//", 1)[1].split(":", 1)[0]

    unauthenticated = requests.get(
        f"{service.service_url}/api/tags",
        headers={"Host": host},
        verify=False,
        timeout=30,
    )
    assert unauthenticated.status_code == 401

    authenticated = requests.get(
        f"{service.service_url}/api/tags",
        auth=(service.user, service.pw),
        headers={"Host": host},
        verify=False,
        timeout=30,
    )
    assert authenticated.status_code == 200
    assert "models" in authenticated.json()
