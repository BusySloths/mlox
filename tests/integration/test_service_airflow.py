import random
import time
import pytest
import logging

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

# Mark this module as an integration test
pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def install_airflow_service(ubuntu_docker_server):
    """Install and start the Airflow service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Load Airflow stack config
    config = load_config(get_stacks_path(), "/airflow", "mlox.3.1.3.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Airflow service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
        # Allow some time for containers to become healthy
        # Downloading images and starting containers may take time

    for i in range(10):
        logger.info(f"Waiting 30s for Airflow service to stabilize... ({i + 1}/10)")
        time.sleep(30)

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


def test_airflow_service_is_running(install_airflow_service):
    """Verify Airflow service is reported as running and exposes a URL."""
    bundle, service = install_airflow_service

    # perform a simple HTTP check against the webserver API if available
    web_url = service.service_urls.get("Airflow UI", None)
    assert web_url, "Airflow UI URL not found in service URLs"

    # Check service status via its check() method
    retries = 40
    for i in range(retries):
        try:
            with bundle.server.get_server_connection() as conn:
                status = service.check(conn)
            if status.get("status") == "running":
                break
            logger.warning(
                f"Retry {i + 1}/{retries} in 60s. Service state is {service.state} but Airflow service not yet up: {status}"
            )
            time.sleep(60)
        except Exception as e:
            status = {"status": "unknown", "error": str(e)}
            logger.warning(
                f"Retry {i + 1}/{retries} in 60s. Exception during status check: {e}"
            )

    assert status.get("status") == "running"
    # state may be 'running' depending on service implementation
    assert service.state == "running"
