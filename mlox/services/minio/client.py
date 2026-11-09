"""S3-compatible implementation of the object-storage client contract."""
from __future__ import annotations

import tempfile
from typing import Any

from mlox.object_storage import AbstractObjectStorageClient


class S3ObjectStorageClient(AbstractObjectStorageClient):
    def __init__(self, endpoint: str, access_key: str, secret_key: str, *,
                 certificate: str = "", region: str = "us-east-1") -> None:
        try:
            import boto3
        except ImportError as exc:
            raise ImportError("Install the MinIO extra: pip install 'busysloths-mlox[minio]'") from exc
        self._certificate_file: Any = None
        verify: bool | str = True
        if certificate:
            self._certificate_file = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="mlox-s3-ca-", suffix=".pem")
            self._certificate_file.write(certificate)
            self._certificate_file.flush()
            verify = self._certificate_file.name
        try:
            self._client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key,
                                        aws_secret_access_key=secret_key, region_name=region,
                                        verify=verify)
        except BaseException:
            if self._certificate_file:
                self._certificate_file.close()
            raise

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        return [obj["Key"] for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
                for obj in page.get("Contents", [])]

    def read_bytes(self, bucket: str, key: str) -> bytes:
        body = self._client.get_object(Bucket=bucket, Key=key)["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def write_bytes(self, bucket: str, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=bucket, Key=key, Body=data)

    def close(self) -> None:
        self._client.close()
        if self._certificate_file:
            self._certificate_file.close()
            self._certificate_file = None

    def __enter__(self) -> S3ObjectStorageClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
