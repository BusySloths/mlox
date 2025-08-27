import os
import time
import pytest

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle


# mark this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_feast_service(ubuntu_docker_server):
    """Install and start the MLflow service on the provided server."""
    # Prepare infrastructure with the existing server
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Load the feast server config from stacks
    config = load_config(get_stacks_path(), "/feast", "mlox.feast.yaml")

    # Install service
    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add feast service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
        # Allow some time for containers to become healthy
        time.sleep(10)

    yield bundle_added, service

    # Teardown after tests
    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception:
            pass
        try:
            service.teardown(conn)
        except Exception:
            pass
    infra.remove_bundle(bundle_added)


def test_feast_service_is_running(install_feast_service):
    """Verify Feast service is installed and reports running."""
    bundle, service = install_feast_service
    assert service.service_url

    with bundle.server.get_server_connection() as conn:
        status = service.check(conn)
    assert status.get("status") == "running"
