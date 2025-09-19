import shlex
import pytest

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

from tests.integration.conftest import wait_for_service_ready


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_minio_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(
        get_stacks_path(), "/minio", "mlox.minio.RELEASE.2024-09-10.yaml"
    )

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add MinIO service from config")

    bundle = bundle_added
    service = bundle.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=20, no_checks=True)

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


def test_minio_service_is_installed(install_minio_service):
    _, service = install_minio_service
    assert service.service_url
    assert service.console_url
    assert service.state == "running"


def test_minio_service_is_running(install_minio_service):
    bundle, service = install_minio_service

    status = wait_for_service_ready(service, bundle, retries=6, interval=20)
    assert status.get("status") == "running"


@pytest.mark.parametrize("bucket", ["mlox-minio-integration"])
def test_minio_basic_read_write(install_minio_service, bucket):
    bundle, service = install_minio_service

    endpoint = shlex.quote(service.service_url)
    access_key = shlex.quote(service.root_user)
    secret_key = shlex.quote(service.root_password)
    bucket_target = shlex.quote(f"local/{bucket}")
    with bundle.server.get_server_connection() as conn:
        conn.run(
            "docker run --rm --network host minio/mc sh -c "
            f"\"mc alias set local {endpoint} {access_key} {secret_key} --insecure "
            f"&& mc mb --ignore-existing --insecure {bucket_target}\"",
            hide=False,
        )

        conn.run(
            "docker run --rm --network host minio/mc sh -c "
            f"\"mc alias set local {endpoint} {access_key} {secret_key} --insecure "
            f"&& printf 'hello from mlox' | mc pipe --insecure {bucket_target}/sample.txt\"",
            hide=False,
        )

        result = conn.run(
            "docker run --rm --network host minio/mc sh -c "
            f"\"mc alias set local {endpoint} {access_key} {secret_key} --insecure "
            f"&& mc cat --insecure {bucket_target}/sample.txt\"",
            hide=True,
        )

    assert "hello from mlox" in result.stdout
