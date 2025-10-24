import pytest

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle
from mlox.services.openbao.client import OpenBaoSecretManager

from tests.integration.conftest import wait_for_service_ready

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_openbao_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/openbao", "mlox.openbao.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add OpenBao service from config")

    bundle = bundle_added
    service = bundle.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=20, no_checks=True)

    yield infra, bundle, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception:
            pass
        try:
            service.teardown(conn)
        except Exception:
            pass
    infra.remove_bundle(bundle)


def test_openbao_service_is_running(install_openbao_service):
    infra, bundle, service = install_openbao_service
    status = wait_for_service_ready(service, bundle, retries=6, interval=20)
    assert status.get("status") == "running"
    assert service.service_url


def test_openbao_secret_roundtrip(install_openbao_service):
    infra, _bundle, service = install_openbao_service

    sm = service.get_secret_manager(infra)
    assert isinstance(sm, OpenBaoSecretManager)
    assert sm.is_working()

    secret_name = "integration-secret"
    secret_payload = {"alpha": 1, "beta": "value"}

    sm.save_secret(secret_name, secret_payload)
    assert sm.load_secret(secret_name) == secret_payload

    listed = sm.list_secrets(keys_only=False)
    assert secret_name in listed and listed[secret_name] == secret_payload

    keys_only = sm.list_secrets(keys_only=True)
    assert secret_name in keys_only and keys_only[secret_name] is None

    secrets = service.get_secrets()
    assert "openbao_root_credentials" in secrets
    assert secrets["openbao_root_credentials"].get("token") == service.root_token
    assert secrets["openbao_root_credentials"].get("verify_tls") == service.verify_tls
