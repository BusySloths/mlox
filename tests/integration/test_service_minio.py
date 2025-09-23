import boto3
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
        get_stacks_path(), "/minio", "mlox.minio.RELEASE.2025-07-23.yaml"
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
    # Use boto3 S3 client to interact with MinIO
    bundle, service = install_minio_service

    _ = wait_for_service_ready(service, bundle, retries=3, interval=10, no_checks=True)

    # service.service_url is like https://<host>:<port>
    # boto3 expects endpoint_url without scheme when using signature_version, so pass full URL
    endpoint = service.service_url
    access_key = service.root_user
    secret_key = service.root_password

    s3 = boto3.resource(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        verify=False,
    )

    bucket_name = bucket
    key = "sample.txt"
    body = b"hello from mlox"

    # create bucket if not exists
    try:
        s3.create_bucket(Bucket=bucket_name)
    except Exception as e:
        pytest.fail(f"Failed to create bucket {bucket_name}: {e}")

    # upload object
    bucket = s3.Bucket(bucket_name)
    bucket.put_object(Key=key, Body=body)

    # read back
    res = bucket.Object(key).get()
    data = res["Body"].read()
    assert data == body

    # cleanup
    bucket.Object(key).delete()
    try:
        bucket.delete()
    except Exception:
        pass
