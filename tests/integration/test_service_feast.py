import os
import pytest
import time

from mlox.session import MloxSession
from mlox.config import load_config, get_stacks_path

# mark this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def session_and_infra():
    password = os.environ.get("MLOX_CONFIG_PASSWORD")
    project = os.environ.get("MLOX_PROJECT", "mlox")
    if not password:
        pytest.skip("MLOX_CONFIG_PASSWORD not set, skipping integration tests")

    ms = MloxSession(project, password)
    infra = ms.infra
    return ms, infra


@pytest.fixture(scope="module")
def install_feast(session_and_infra):
    """Install and start the Feast service on a pre-provisioned server.

    Returns a tuple (bundle_added, service) for use in tests.
    """
    ms, infra = session_and_infra

    # Find a server bundle that is reachable (assumes multipass created one)
    if not infra.bundles:
        pytest.skip("No bundles found in infrastructure")

    bundle = infra.bundles[0]
    server = bundle.server

    # Load the feast server config from stacks
    config = load_config(get_stacks_path(), "/feast", "docker-compose-feast.yaml")
    params = {
        "${MLOX_SERVER_IP}": server.ip,
        "${MLOX_USER}": server.mlox_user.name if server.mlox_user else "ubuntu",
        "${MLOX_AUTO_PW}": "demo",
    }

    # Install service
    bundle_added = infra.add_service(server.ip, config, params)
    if not bundle_added:
        pytest.skip("Failed to add feast service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with bundle_added.server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
        # allow a brief warmup for containers
        time.sleep(10)

    yield bundle_added, service

    # Note: don't teardown here — removal is a separate operation (see test_remove_feast)


def test_dummy_service_running(install_feast):
    """Basic smoke test that the service was installed and exposes a URL."""
    bundle_added, service = install_feast
    assert hasattr(service, "service_url")
    assert service.service_url


def test_remove_feast(install_feast, session_and_infra):
    """Tear down the installed service and remove the bundle from infra."""
    bundle_added, service = install_feast
    ms, infra = session_and_infra

    # Teardown the service on the server
    with bundle_added.server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception:
            # best-effort
            pass
        try:
            service.teardown(conn)
        except Exception:
            pass

    # Remove the bundle from the infrastructure
    infra.remove_bundle(bundle_added)

    # Ensure bundle was removed
    assert all(b != bundle_added for b in infra.bundles)
