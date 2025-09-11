import logging
import pytest
import redis

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

from tests.integration.conftest import wait_for_service_ready


pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def install_redis_service(ubuntu_docker_server):
    """Install and start the Redis service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Load Redis stack config
    config = load_config(get_stacks_path(), "/redis", "mlox.redis.8.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Redis service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=30, no_checks=True)

    yield bundle_added, service

    # Teardown after tests
    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service spin_down for teardown: {e}")
        try:
            service.teardown(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service teardown: {e}")
    infra.remove_bundle(bundle_added)


def test_redis_service_is_running(install_redis_service):
    bundle, service = install_redis_service
    wait_for_service_ready(service, bundle, retries=60, interval=10)

    status = {}
    try:
        with bundle.server.get_server_connection() as conn:
            # client = redis.Redis(
            #     host=service.params.get("host", "localhost"),
            #     port=service.params.get("port", 6379),
            #     password=service.params.get("password", None),
            #     decode_responses=True,
            # )
            # pong = client.ping()
            # assert pong is True
            status = service.check(conn)
    except Exception as e:
        logger.error(f"Error checking Postgres service status: {e}")

    assert status.get("status", None) == "running"
