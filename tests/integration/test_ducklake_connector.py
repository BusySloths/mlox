"""Opt-in service → collected secret → DuckLake client integration.

The suite's Multipass VM hosts real MLOX PostgreSQL and MinIO deployments.
See ducklake_connector.md for prerequisites and cleanup.
"""
from types import SimpleNamespace
import uuid

import pytest

from mlox.application.use_cases.secrets import collect_service_secrets
from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from mlox.project.repository import SqlCipherRepository
from mlox.project.secrets import EmbeddedSecretManager
from mlox.services.ducklake.client import DuckLakeClient
from mlox.tui.services.setup import _ducklake_params
from tests.integration.conftest import wait_for_service_ready
from tests.integration.helpers import add_service, prepare_service, remove_service

pytestmark = pytest.mark.integration


@pytest.fixture
def lake_environment(tmp_path, request):
    # Check local dependencies before allocating the suite's disposable VM.
    pytest.importorskip("duckdb")
    pytest.importorskip("pandas")
    boto3 = pytest.importorskip("boto3")
    server = request.getfixturevalue("ubuntu_docker_server")
    infra = Infrastructure()
    bundle = Bundle(name=server.ip, server=server)
    infra.bundles.append(bundle)
    name = f"test_{uuid.uuid4().hex}"
    bucket = f"mlox-{uuid.uuid4().hex}"

    def install(directory, filename, params):
        config = load_config(get_stacks_path(), directory, filename)
        added = add_service(infra, server.ip, config, params=params)
        assert added is bundle, f"Failed to add {config.id}"
        service = bundle.services[-1]
        # Registers removal before setup, including partial setup failures.
        prepare_service(request, infra, bundle, service)
        assert wait_for_service_ready(service, bundle, retries=30, interval=5).get("status") == "running"
        return service

    postgres = install("/postgres", "mlox.postgres.16.yaml", {"${POSTGRES_DB}": name})
    storage = install("/minio", "mlox.minio.RELEASE.2025-07-23.yaml", {})
    assert postgres.certificate and storage.certificate
    ca_file = tmp_path / "minio-ca.pem"
    ca_file.write_text(storage.certificate)
    s3 = boto3.client("s3", endpoint_url=storage.service_url,
                      aws_access_key_id=storage.root_user,
                      aws_secret_access_key=storage.root_password,
                      region_name="us-east-1", verify=str(ca_file))
    request.addfinalizer(s3.close)
    s3.create_bucket(Bucket=bucket)

    def cleanup_bucket():
        # Runs before service removal; the VM teardown remains the final safety
        # net for metadata, volumes and objects if any cleanup operation fails.
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        s3.delete_bucket(Bucket=bucket)

    request.addfinalizer(cleanup_bucket)
    repository = SqlCipherRepository.create(tmp_path / "lake.mlox", "integration-password")
    manager = EmbeddedSecretManager(repository)
    workspace = SimpleNamespace(infrastructure=infra, secrets=manager)
    config = load_config(get_stacks_path(), "/ducklake", "mlox.ducklake.yaml")

    def setup_connector():
        params = _ducklake_params({"lake_name": name, "bucket": bucket,
                                  "postgres_service_uuid": postgres.uuid,
                                  "storage_service_uuid": storage.uuid}, infra)
        added = add_service(infra, server.ip, config, params=params)
        assert added is bundle
        service = bundle.services[-1]
        def cleanup_connector():
            if infra.get_service_by_uuid(service.uuid) is not None:
                assert remove_service(infra, service.name).success

        request.addfinalizer(cleanup_connector)
        service.setup(None)
        assert service.state == "running"
        assert service.secret_manager_uuid == ""
        assert service.postgres_secret_name == service.s3_secret_name == ""
        return service

    service = setup_connector()
    print(f"DuckLake test metadata schema: {service.metadata_schema}; prefix: {service.data_path}")
    return SimpleNamespace(service=service, setup_connector=setup_connector,
                           workspace=workspace, manager=manager, bundle=bundle,
                           storage=storage, s3=s3, bucket=bucket)


def collect(env, service):
    result = collect_service_secrets(env.workspace, "embedded")
    assert result.success
    assert result.data["errors"] == []
    assert service.uuid in {item["uuid"] for item in result.data["services"]}
    secret = env.manager.load_secret(service.uuid)
    assert secret == service.get_secrets()
    assert secret["postgres_connection"]["certificate"]
    assert secret["s3_connection"]["certificate"]
    assert secret["ducklake_connection"]["service_uuid"] == service.uuid
    return DuckLakeClient.from_secret(env.manager, service.uuid)


def test_ducklake_postgres_s3_roundtrip(lake_environment):
    import duckdb
    import pandas as pd

    env = lake_environment
    service = env.service
    assert env.manager.load_secret(service.uuid) is None
    client = collect(env, service)
    with pytest.raises(duckdb.InvalidInputException, match="does not exist"):
        with client.connect():
            pass  # Setup and collection must not initialize the lake.
    client.create_lake()
    frame = pd.DataFrame({"id": list(range(200)), "value": ["data"] * 200})
    extra = pd.DataFrame({"id": [200], "value": ["appended"]})
    client.write_dataframe("items", frame, mode="create")
    client.write_dataframe("items", extra, mode="append")
    expected = pd.concat([frame, extra], ignore_index=True)

    def assert_contents(reader):
        assert reader.query("SELECT count(*), sum(id) FROM items") == [(201, 20100)]
        assert reader.query("SELECT value FROM items WHERE id = ?", [200]) == [("appended",)]
        pd.testing.assert_frame_equal(reader.read_dataframe("SELECT * FROM items ORDER BY id"), expected)
        assert reader.list_tables() == ["items"]
        assert reader.check() == {"status": "running"}

    assert_contents(client)
    prefix = service.data_path.removeprefix(f"s3://{env.bucket}/")
    assert env.s3.list_objects_v2(Bucket=env.bucket, Prefix=prefix).get("KeyCount", 0) > 0
    assert service.check(None) == {"status": "running"}
    assert_contents(DuckLakeClient.from_secret(env.manager, service.uuid))

    # Change a real connection option, then recollect. The existing portable
    # client must load the updated credentials/options on its next connection.
    before = env.manager.load_secret(service.uuid)
    env.storage.service_url = env.storage.service_url.rstrip("/") + "/"
    assert env.manager.load_secret(service.uuid) == before
    collect(env, service)
    assert env.manager.load_secret(service.uuid)["s3_connection"]["endpoint"] == env.storage.service_url
    assert env.manager.load_secret(service.uuid) != before
    assert_contents(client)

    # Removing a virtual connector must preserve both backing services and data.
    result = remove_service(env.workspace.infrastructure, service.name)
    assert result.success
    assert service.state == "un-initialized"
    replacement = env.setup_connector()
    assert replacement.uuid != service.uuid
    assert (replacement.catalog_name, replacement.metadata_schema, replacement.data_path) == (
        service.catalog_name, service.metadata_schema, service.data_path)
    # No create_lake call: a missing catalog must fail recovery instead of being
    # silently replaced with an empty lake.
    assert_contents(replacement.get_client(env.workspace.infrastructure))
    assert_contents(collect(env, replacement))
