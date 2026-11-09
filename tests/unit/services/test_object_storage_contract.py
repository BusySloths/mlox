from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from mlox.config import load_all_service_configs
from mlox.object_storage import AbstractObjectStorageClient
from mlox.service import AbstractObjectStorageService, AbstractS3ObjectStorageService, ServiceCapability
from mlox.services.gcp.storage_service import GCPStorageService
from mlox.services.minio.docker import MinioDockerService


def test_storage_service_contract_and_capability_declarations():
    assert issubclass(MinioDockerService, AbstractS3ObjectStorageService)
    assert issubclass(GCPStorageService, AbstractObjectStorageService)
    assert not issubclass(GCPStorageService, AbstractS3ObjectStorageService)
    configs = {c.id: c for c in load_all_service_configs()}
    assert ServiceCapability.S3_OBJECT_STORAGE in configs["minio-release-2025-07-23-docker"].service_capabilities()
    assert ServiceCapability.S3_OBJECT_STORAGE not in configs["gcp-storage-0.1.0"].service_capabilities()


def test_s3_client_paginates_and_moves_binary_data(monkeypatch):
    import boto3
    from mlox.services.minio.client import S3ObjectStorageClient

    api = Mock()
    api.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "a"}]}, {}, {"Contents": [{"Key": "b"}]},
    ]
    body = BytesIO(b"\x00\xff")
    api.get_object.return_value = {"Body": body}
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: api)
    with S3ObjectStorageClient("https://s3.example", "key", "secret") as client:
        assert isinstance(client, AbstractObjectStorageClient)
        assert client.list_keys("bucket", "a/") == ["a", "b"]
        assert client.read_bytes("bucket", "key") == b"\x00\xff"
        assert body.closed
        client.write_bytes("bucket", "key", b"\x00\xff")
    api.put_object.assert_called_once_with(Bucket="bucket", Key="key", Body=b"\x00\xff")
    api.close.assert_called_once()


def test_gcs_client_supports_common_binary_contract(monkeypatch):
    from mlox.services.gcp.cloud_storage import GCPStorage

    blob = Mock()
    blob.download_as_bytes.return_value = b"\x00\xff"
    bucket = Mock()
    bucket.blob.return_value = blob
    google = Mock()
    google.bucket.return_value = bucket
    google.list_blobs.return_value = [SimpleNamespace(name="prefix/object")]
    client = GCPStorage.__new__(GCPStorage)
    monkeypatch.setattr(client, "_get_storage_client", lambda: google)
    assert isinstance(client, AbstractObjectStorageClient)
    assert client.list_keys("bucket", "prefix/") == ["prefix/object"]
    assert client.read_bytes("bucket", "object") == b"\x00\xff"
    client.write_bytes("bucket", "object", b"\x00\xff")
    blob.upload_from_string.assert_called_once_with(b"\x00\xff")


def test_minio_exports_endpoint_and_certificate():
    service = MinioDockerService(name="m", service_config_id="minio", template="x", target_path="/tmp/m", root_user="u", root_password="p", api_port=9000, console_port=9001)
    service.service_url = "https://minio.example:9000"
    service.certificate = "CA certificate"
    assert service.get_secrets()["s3_connection"] == service.get_secrets()["minio_root_credentials"]
    assert service.get_secrets()["minio_root_credentials"] == {
        "username": "u", "password": "p", "endpoint": "https://minio.example:9000", "certificate": "CA certificate",
    }
