import os
import pytest
from pathlib import Path

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from mlox.services.feast.client import (
    cleanup_repo_config,
    get_repo_config,
)
from mlox.services.feast.docker import FeastDockerService
from mlox.services.postgres.docker import PostgresDockerService
from mlox.services.redis.docker import RedisDockerService
from mlox.secret_manager import (
    InMemorySecretManager,
    get_encrypted_access_keyfile,
)

from tests.integration.conftest import wait_for_service_ready


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_feast_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Install Redis online store
    redis_config = load_config(get_stacks_path(), "/redis", "mlox.redis.8.yaml")
    redis_bundle = infra.add_service(ubuntu_docker_server.ip, redis_config, params={})
    if not redis_bundle:
        pytest.skip("Failed to add Redis service")
    redis_service = next(
        (svc for svc in redis_bundle.services if isinstance(svc, RedisDockerService)),
        None,
    )
    assert redis_service is not None, "Redis service not created"
    with ubuntu_docker_server.get_server_connection() as conn:
        redis_service.setup(conn)
        redis_service.spin_up(conn)
    wait_for_service_ready(redis_service, redis_bundle, interval=5, retries=12)

    # Install Postgres offline store
    postgres_config = load_config(
        get_stacks_path(), "/postgres", "mlox.postgres.16.yaml"
    )
    postgres_params = {"${POSTGRES_DB}": "feast_integration"}
    postgres_bundle = infra.add_service(
        ubuntu_docker_server.ip, postgres_config, params=postgres_params
    )
    if not postgres_bundle:
        pytest.skip("Failed to add Postgres service")
    postgres_service = next(
        (
            svc
            for svc in postgres_bundle.services
            if isinstance(svc, PostgresDockerService)
        ),
        None,
    )
    assert postgres_service is not None, "Postgres service not created"
    with ubuntu_docker_server.get_server_connection() as conn:
        postgres_service.setup(conn)
        postgres_service.spin_up(conn)
    wait_for_service_ready(postgres_service, postgres_bundle, interval=5, retries=12)

    feast_config = load_config(get_stacks_path(), "/feast", "mlox.feast.yaml")
    params = {
        "${FEAST_PROJECT_NAME}": "feast_integration",
        "${ONLINE_STORE_UUID}": redis_service.uuid,
        "${OFFLINE_STORE_UUID}": postgres_service.uuid,
    }
    feast_bundle = infra.add_service(
        ubuntu_docker_server.ip, feast_config, params=params
    )
    if not feast_bundle:
        pytest.skip("Failed to add Feast service")
    feast_service = next(
        (svc for svc in feast_bundle.services if isinstance(svc, FeastDockerService)),
        None,
    )
    assert feast_service is not None, "Feast service not created"
    with ubuntu_docker_server.get_server_connection() as conn:
        feast_service.setup(conn)
        feast_service.spin_up(conn)
    wait_for_service_ready(feast_service, feast_bundle, interval=10, retries=18)

    yield infra, feast_bundle, feast_service, redis_service, postgres_service

    with ubuntu_docker_server.get_server_connection() as conn:
        feast_service.spin_down(conn)
        feast_service.teardown(conn)
        postgres_service.spin_down(conn)
        postgres_service.teardown(conn)
        redis_service.spin_down(conn)
        redis_service.teardown(conn)

    infra.remove_bundle(bundle)


def test_feast_service_is_running(install_feast_service):
    _, bundle, service, _, _ = install_feast_service
    assert isinstance(service, FeastDockerService)
    assert service.service_url
    status = wait_for_service_ready(service, bundle, interval=5, retries=3)
    assert status.get("status") == "running"


def test_feast_service_links_remote_stores(install_feast_service):
    infra, _, service, redis_service, postgres_service = install_feast_service
    assert service.online_store_uuid == redis_service.uuid
    assert service.offline_store_uuid == postgres_service.uuid
    secrets = service.get_secrets()
    assert secrets["feast_registry"]["online_store_uuid"] == redis_service.uuid
    assert secrets["feast_registry"]["offline_store_uuid"] == postgres_service.uuid


def test_get_repo_config(install_feast_service):
    infra, _, service, redis_service, postgres_service = install_feast_service
    secret_manager = InMemorySecretManager()

    registry_secret = service.get_secrets()
    secret_manager.save_secret(
        "MLOX_SERVICE_NAME_UUID_MAP", {service.name: service.uuid}
    )
    secret_manager.save_secret(service.uuid, registry_secret)

    redis_connection = {
        "host": redis_service.service_urls["Redis IP"],
        "port": int(redis_service.port),
        "password": redis_service.pw,
        "certificate": redis_service.certificate,
    }
    secret_manager.save_secret(
        service.online_store_uuid, {"redis_connection": redis_connection}
    )

    postgres_connection = {
        "host": postgres_service.service_urls["Postgres IP"],
        "port": int(postgres_service.port),
        "database": postgres_service.db,
        "username": postgres_service.user,
        "password": postgres_service.pw,
        "certificate": postgres_service.certificate,
    }
    secret_manager.save_secret(
        service.offline_store_uuid, {"postgres_connection": postgres_connection}
    )

    password = "test-secret"
    keyfile_name = f".feast_repo_key_{service.uuid}.json"
    keyfile_path = Path(os.getcwd()) / keyfile_name
    keyfile_path.write_bytes(
        get_encrypted_access_keyfile(secret_manager, password).encode("utf-8")
    )

    repo_config, tmpdir = get_repo_config(service.name, f"/{keyfile_name}", password)
    try:
        registry_cfg = registry_secret["feast_registry"]
        assert repo_config.project == registry_cfg["project"]
        assert repo_config.registry.path == (
            f"{registry_cfg['registry_host']}:{registry_cfg['registry_port']}"
        )

        connection_string = repo_config.online_store.connection_string
        assert connection_string.startswith(
            f"{redis_connection['host']}:{redis_connection['port']}"
        )

        assert repo_config.offline_store.host == postgres_connection["host"]
        assert repo_config.offline_store.port == postgres_connection["port"]
    finally:
        cleanup_repo_config(tmpdir)
        keyfile_path.unlink(missing_ok=True)
