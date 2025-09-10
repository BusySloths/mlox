import time
import pytest

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle


# Mark this module as an integration test
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_milvus_service(ubuntu_docker_server):
    """Install and start the Milvus service on the provided server."""
    # Prepare infrastructure with the existing server
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Load Milvus service configuration
    config = load_config(get_stacks_path(), "/milvus", "mlox.milvus.2.5.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Milvus service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
        # Allow some time for containers to become healthy
    time.sleep(30)

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


def test_milvus_service_is_running(install_milvus_service):
    """Verify Milvus service is reported as running and exposes a URL."""
    _, service = install_milvus_service
    assert service.service_url
    assert service.state == "running"


# ---- Stubs for future Milvus tests (intentionally skipped) ----


@pytest.mark.skip(reason="Not implemented: verify client connection")
def test_milvus_client_connection():
    """Connect to Milvus using pymilvus and verify basic connectivity."""
    pass


@pytest.mark.skip(reason="Not implemented: create collection")
def test_milvus_create_collection():
    """Create a test collection with a simple schema."""
    pass


@pytest.mark.skip(reason="Not implemented: insert vectors")
def test_milvus_insert_vectors():
    """Insert sample vectors into the created collection and verify counts."""
    pass


@pytest.mark.skip(reason="Not implemented: search vectors")
def test_milvus_search_vectors():
    """Run a similarity search against inserted vectors and validate results."""
    pass


@pytest.mark.skip(reason="Not implemented: delete collection")
def test_milvus_delete_collection():
    """Delete the test collection and ensure it is removed."""
    pass
