import yaml
import pytest

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from mlox.services.feast.client import (
    cleanup_repo_config,
    materialize_feature_store_config,
)
from mlox.services.feast.docker import FeastDockerService
from mlox.services.postgres.docker import PostgresDockerService
from mlox.services.redis.docker import RedisDockerService

from .conftest import wait_for_service_ready


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
        "${ONLINE_STORE_SERVICE}": redis_service,
        "${OFFLINE_STORE_SERVICE}": postgres_service,
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
    assert secrets["feast_online_store"]["service_uuid"] == redis_service.uuid
    assert secrets["feast_offline_store"]["service_uuid"] == postgres_service.uuid


def test_materialize_feature_store_config(install_feast_service):
    infra, _, service, redis_service, postgres_service = install_feast_service
    tmpdir = materialize_feature_store_config(infra, service.name)
    try:
        cfg_path = tmpdir / "feature_store.yaml"
        assert cfg_path.exists()
        config = yaml.safe_load(cfg_path.read_text())
        assert config["online_store"]["connection_string"].endswith(
            f"{infra.get_bundle_by_service(redis_service).server.ip}:{redis_service.service_ports['Redis']}"
        )
        assert (
            config["offline_store"]["host"]
            == infra.get_bundle_by_service(postgres_service).server.ip
        )
        assert (
            config["offline_store"]["port"]
            == postgres_service.service_ports["Postgres"]
        )
    finally:
        cleanup_repo_config(tmpdir)
