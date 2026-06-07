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
    assert service.root_token
    assert service.unseal_keys
    assert service.admin_username
    assert service.admin_password
    assert service.client_token
    assert service.client_token != service.root_token


def test_openbao_secret_roundtrip(install_openbao_service):
    infra, _bundle, service = install_openbao_service

    sm = service.get_secret_manager(infra)
    assert isinstance(sm, OpenBaoSecretManager)
    assert sm.is_working()
    assert sm.address.startswith("https://")
    assert sm.token == service.client_token

    secret_name = "integration-secret"
    secret_payload = {"alpha": 1, "beta": "value"}

    sm.save_secret(secret_name, secret_payload)
    assert sm.load_secret(secret_name) == secret_payload

    listed = sm.list_secrets(keys_only=False)
    assert secret_name in listed and listed[secret_name] == secret_payload

    keys_only = sm.list_secrets(keys_only=True)
    assert secret_name in keys_only and keys_only[secret_name] is None

    secrets = service.get_secrets()
    assert "openbao_client_credentials" in secrets
    assert "openbao_root_credentials" not in secrets
    creds = secrets["openbao_client_credentials"]
    assert creds.get("token") == service.client_token
    assert creds.get("token") != service.root_token
    assert "root_token" not in creds
    assert "unseal_keys" not in creds
    assert creds.get("address", "").startswith("https://")
    assert creds.get("verify_tls") is False
    assert service.compose_service_names["OpenBao"].endswith("_openbao")


def test_openbao_restart_preserves_raft_data(install_openbao_service):
    infra, bundle, service = install_openbao_service
    sm = service.get_secret_manager(infra)
    secret_name = "integration-restart-secret"
    secret_payload = {"persisted": True}
    sm.save_secret(secret_name, secret_payload)

    with bundle.server.get_server_connection() as conn:
        service.spin_down(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=20)
    sm = service.get_secret_manager(infra)
    assert sm.load_secret(secret_name) == secret_payload


def test_openbao_create_token_allows_child_access(install_openbao_service):
    infra, _bundle, service = install_openbao_service
    sm = service.get_root_secret_manager(infra)

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
    sm = service.get_root_secret_manager(infra)

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


def test_openbao_userpass_login_and_client_token_renewal(install_openbao_service):
    infra, _bundle, service = install_openbao_service
    root_manager = service.get_root_secret_manager(infra)

    user_auth = root_manager.login_userpass(
        service.admin_username, service.admin_password, path=service.userpass_path
    )
    assert user_auth.get("client_token")
    assert user_auth.get("client_token") != service.root_token

    previous_token = service.client_token
    auth = service.renew_client_token(infra, increment="10m")
    assert auth.get("lease_duration", 0) > 0
    assert service.client_token
    assert service.client_token == auth.get("client_token", previous_token)
    assert service.client_token_lease_duration > 0


def test_openbao_secret_manager_is_self_contained(install_openbao_service):
    infra, _bundle, service = install_openbao_service
    secret_name = "integration-self-contained"
    secret_payload = {"self_contained": True}

    sm = service.get_secret_manager(infra)
    sm.save_secret(secret_name, secret_payload)
    access = sm.get_access_secrets()
    assert access
    assert access.get("token") == service.client_token
    assert access.get("token") != service.root_token
    assert "unseal_keys" not in access
    assert "root_token" not in access

    restored = OpenBaoSecretManager.instantiate_secret_manager(access)
    assert restored is not None
    assert restored.load_secret(secret_name) == secret_payload
