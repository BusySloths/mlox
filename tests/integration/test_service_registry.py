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
def install_registry_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/registry", "mlox.registry.3.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add registry service from config")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=20, no_checks=True)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception as exc:
            logger.warning("Error during registry spin_down: %s", exc)
        try:
            service.teardown(conn)
        except Exception as exc:
            logger.warning("Error during registry teardown: %s", exc)
    infra.remove_bundle(bundle_added)


def test_registry_service_running(install_registry_service):
    _, service = install_registry_service
    assert service.service_urls.get("Registry")
    assert service.state == "running"


def test_registry_requires_authentication(install_registry_service):
    _, service = install_registry_service
    url = service.service_urls.get("Registry")
    assert url is not None

    response = requests.get(f"{url}/v2/_catalog", verify=False, timeout=15)
    assert response.status_code == 401


def test_registry_allows_authenticated_access(install_registry_service):
    _, service = install_registry_service
    url = service.service_urls.get("Registry")
    assert url is not None

    response = requests.get(
        f"{url}/v2/_catalog",
        verify=False,
        timeout=15,
        auth=(service.username, service.password),
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload.get("repositories"), list)
