import pytest

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle
from mlox.services.openbao.client import OpenBaoSecretManager
from mlox.utils import generate_password

from tests.integration.conftest import wait_for_service_ready

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_openbao_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/openbao", "mlox.openbao.yaml")

    params = {
        "${OPENBAO_ROOT_TOKEN}": generate_password(length=20, with_punctuation=False)
    }
    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params=params)
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
    assert sm.address.startswith("https://")

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
    creds = secrets["openbao_root_credentials"]
    assert creds.get("token") == service.root_token
    assert creds.get("address", "").startswith("https://")
    assert creds.get("verify_tls") is False
    assert service.compose_service_names["OpenBao"].endswith("_openbao")


def test_openbao_create_token_allows_child_access(install_openbao_service):
    infra, _bundle, service = install_openbao_service
    sm = service.get_secret_manager(infra)

    secret_name = "integration-token-secret"
    secret_payload = {"token": generate_password(length=16, with_punctuation=False)}
    sm.save_secret(secret_name, secret_payload)

    auth = sm.create_token(
        ttl=180,
        metadata={"purpose": "integration-test"},
    )
    child_token = auth.get("client_token")
    assert child_token
    assert child_token != service.root_token
    assert auth.get("lease_duration", 0) >= 180

    child_manager = OpenBaoSecretManager(
        address=sm.address,
        token=child_token,
        mount_path=sm.mount_path,
        verify_tls=sm.verify_tls,
    )
    assert child_manager.load_secret(secret_name) == secret_payload

    lookup = sm._request(
        "POST",
        "/v1/auth/token/lookup",
        data={"token": child_token},
    )
    info = lookup.get("data", {})
    assert info.get("meta", {}).get("purpose") == "integration-test"
    assert info.get("ttl", 0) >= 150
    assert info.get("renewable") is True


def test_openbao_create_token_honors_options(install_openbao_service):
    infra, _bundle, service = install_openbao_service
    sm = service.get_secret_manager(infra)

    auth = sm.create_token(
        ttl="90s",
        renewable=False,
        num_uses=2,
    )
    assert auth.get("client_token")
    assert auth.get("client_token") != service.root_token
    assert 0 < auth.get("lease_duration", 0) <= 90

    lookup = sm._request(
        "POST",
        "/v1/auth/token/lookup",
        data={"token": auth["client_token"]},
    )
    info = lookup.get("data", {})
    ttl_seconds = info.get("ttl", 0)
    assert 0 < ttl_seconds <= 90
    assert info.get("renewable") is False
    assert info.get("num_uses") == 2
