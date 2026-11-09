"""Optional integration test against disposable PostgreSQL and S3 services.

Set MLOX_DUCKLAKE_TEST_POSTGRES and MLOX_DUCKLAKE_TEST_S3 to JSON secrets,
plus MLOX_DUCKLAKE_TEST_BUCKET to an existing disposable bucket. This test
creates a new metadata schema and object prefix and does not remove them.
"""
import json
import os
import uuid

import pytest

from mlox.services.ducklake.client import DuckLakeClient


def test_ducklake_postgres_s3_roundtrip():
    pg = os.getenv("MLOX_DUCKLAKE_TEST_POSTGRES")
    s3 = os.getenv("MLOX_DUCKLAKE_TEST_S3")
    bucket = os.getenv("MLOX_DUCKLAKE_TEST_BUCKET")
    if not all((pg, s3, bucket)):
        pytest.skip("DuckLake integration services are not configured")
    duckdb = pytest.importorskip("duckdb")
    pd = pytest.importorskip("pandas")
    secrets = {"pg": json.loads(pg), "s3": json.loads(s3)}

    class Manager:
        def load_secret(self, name):
            return secrets[name]

    suffix = uuid.uuid4().hex
    client = DuckLakeClient(Manager(), "pg", "s3", f"s3://{bucket}/{suffix}/", metadata_schema=f"lake_{suffix}")
    with pytest.raises(duckdb.InvalidInputException, match="does not exist"):
        client.connect()  # The default must not initialize a catalog.
    client.create_lake()
    frame = pd.DataFrame({"id": list(range(200)), "value": ["data"] * 200})
    client.write_dataframe("items", frame, mode="create")
    client.write_dataframe("items", frame.iloc[:1], mode="append")
    assert client.query("SELECT count(*) FROM items") == [(201,)]
    assert len(client.read_dataframe("SELECT * FROM items")) == 201
    assert client.list_tables() == ["items"]
    assert client.check() == {"status": "running"}
