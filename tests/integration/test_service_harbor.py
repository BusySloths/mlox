import pytest

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

from tests.integration.conftest import wait_for_service_ready


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_harbor_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(
        get_stacks_path(), "/harbor", "mlox.harbor.v2.14.0.yaml"
    )

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Harbor service from config")

    bundle = bundle_added
    service = bundle.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=10, interval=60, no_checks=True)

    yield bundle_added, service

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


def test_harbor_service_is_installed(install_harbor_service):
    _, service = install_harbor_service
    assert service.service_url
    assert service.registry_url
    assert service.state == "running"


def test_harbor_service_is_running(install_harbor_service):
    bundle, service = install_harbor_service

    status = wait_for_service_ready(service, bundle, retries=5, interval=60)
    assert status.get("status") == "running"


def test_harbor_secrets_available(install_harbor_service):
    _, service = install_harbor_service
    secrets = service.get_secrets()
    assert "harbor_admin_credentials" in secrets
    assert secrets["harbor_admin_credentials"]["username"] == service.admin_username
    assert secrets["harbor_admin_credentials"]["password"] == service.admin_password
