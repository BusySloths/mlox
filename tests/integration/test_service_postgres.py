from tests.integration.helpers import add_service, remove_service
import pytest
import logging

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

from tests.integration.conftest import wait_for_service_ready


pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def install_postgres_service(ubuntu_docker_server):
    """Install and start the Postgres service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/postgres", "mlox.postgres.16.yaml")

    bundle_added = add_service(infra, ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Postgres service from config")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=30, interval=10)

    yield bundle_added, service

    result = remove_service(infra, service.name)
    if not result.success:
        logger.warning("Failed to remove service via application logic: %s", result.message)


def test_postgres_service_is_running(install_postgres_service):
    bundle, service = install_postgres_service
    wait_for_service_ready(service, bundle, retries=60, interval=10)

    status = {}
    try:
        with bundle.server.get_server_connection() as conn:
            status = service.check(conn)
    except Exception as e:
        logger.error(f"Error checking Postgres service status: {e}")

    assert status.get("status", None) == "running"
