import logging
import pytest
import redis

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

from .conftest import wait_for_service_ready


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

    def check_fn():
        client = redis.Redis(
            host=ubuntu_docker_server.ip,
            port=int(service.port),
            password=service.pw,
            ssl=True,
            ssl_cert_reqs=None,
        )
        client.ping()
        return {"status": "running"}

    wait_for_service_ready(service, bundle, check_fn=check_fn, retries=40, interval=10)

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


def _redis_client(bundle, service):
    return redis.Redis(
        host=bundle.server.ip,
        port=int(service.port),
        password=service.pw,
        ssl=True,
        ssl_cert_reqs=None,
    )


def test_redis_service_is_running(install_redis_service):
    bundle, service = install_redis_service
    client = _redis_client(bundle, service)
    assert client.ping()


def test_redis_set_get(install_redis_service):
    bundle, service = install_redis_service
    client = _redis_client(bundle, service)
    client.set("mlox", "rocks")
    assert client.get("mlox") == b"rocks"
