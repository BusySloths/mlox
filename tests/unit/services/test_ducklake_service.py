from types import SimpleNamespace
import sys

import pytest

from mlox.service import ServiceCapability
from mlox.services.ducklake.client import DuckLakeClient
from mlox.services.ducklake.service import DuckLakeService


class SecretManager:
    def __init__(self):
        self.values = {
            "postgres": {"host": "pg.example", "port": 5432, "database": "catalog", "username": "owner", "password": "pg-secret"},
            "s3": {"endpoint": "https://minio.example:9000", "username": "key", "password": "s3-secret"},
        }

    def load_secret(self, name):
        return self.values.get(name)

    def list_secrets(self, keys_only=False):
        return self.values


class FakeConnection:
    def __init__(self, data_path="s3://bucket/lake/"):
        self.calls = []
        self.closed = False
        self.data_path = data_path

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        return (self.data_path,)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def client():
    return DuckLakeClient(SecretManager(), "postgres", "s3", "s3://bucket/lake/")


def test_connect_uses_secret_parameters_and_does_not_create_by_default(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda _: conn))
    assert client().connect() is conn
    sql = "\n".join(call[0] for call in conn.calls)
    assert "pg-secret" not in sql and "s3-secret" not in sql
    assert "ATTACH 'ducklake:postgres:'" in sql
    assert "META_SECRET 'mlox_pg'" in sql
    assert "CREATE_IF_NOT_EXISTS false" in sql
    assert "DATA_PATH" not in sql
    assert any("pg-secret" in (params or []) for _, params in conn.calls)


def test_create_and_read_only_modes_are_explicit(monkeypatch):
    connections = []
    def connect(_):
        conn = FakeConnection()
        connections.append(conn)
        return conn
    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=connect))
    client().create_lake()
    attach = next(sql for sql, _ in connections[0].calls if sql.startswith("ATTACH"))
    assert "CREATE_IF_NOT_EXISTS true" in attach
    assert "DATA_PATH 's3://bucket/lake/'" in attach
    assert connections[0].closed
    client().check()
    attach = next(sql for sql, _ in connections[1].calls if sql.startswith("ATTACH"))
    assert "CREATE_IF_NOT_EXISTS false" in attach and "READ_ONLY" in attach
    with pytest.raises(ValueError):
        client().connect(create=True, read_only=True)


def test_existing_data_path_mismatch_closes_connection(monkeypatch):
    conn = FakeConnection("s3://another/lake/")
    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda _: conn))
    with pytest.raises(ValueError, match="data path"):
        client().connect()
    assert conn.closed


def test_missing_secret_and_invalid_paths_fail_safely(monkeypatch):
    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda _: FakeConnection()))
    c = client()
    c.secret_manager.values.pop("postgres")
    with pytest.raises(ValueError, match="must exist"):
        c.connect()
    with pytest.raises(ValueError, match="s3://"):
        DuckLakeClient(SecretManager(), "postgres", "s3", "file:///tmp/lake")


def test_connector_resolves_bound_services_and_manager():
    manager = SecretManager()
    service = DuckLakeService(name="lake", service_config_id="ducklake-1.1-connector", template="ducklake/mlox.ducklake.yaml", target_path="/tmp/lake", postgres_service_uuid="pg", storage_service_uuid="s3", secret_manager_uuid="sm", postgres_secret_name="postgres", s3_secret_name="s3", data_path="s3://bucket/lake/")
    services = {
        "pg": SimpleNamespace(capabilities={ServiceCapability.DATABASE}, service_urls={"Postgres IP": "pg.example"}, port=5432, db="catalog"),
        "s3": SimpleNamespace(service_config_id="minio-release-2025-07-23-docker", capabilities={ServiceCapability.OBJECT_STORAGE, ServiceCapability.S3_OBJECT_STORAGE}, service_urls={"MinIO API": "https://minio.example:9000"}),
        "sm": SimpleNamespace(get_secret_manager=lambda infra: manager),
    }
    infra = SimpleNamespace(get_service_by_uuid=services.get)
    resolved = service.get_client(infra)
    assert resolved.secret_manager is manager
    assert resolved.postgres_defaults["host"] == "pg.example"
    assert resolved.s3_defaults["endpoint"] == "https://minio.example:9000"
    services["s3"].capabilities = {ServiceCapability.OBJECT_STORAGE}
    with pytest.raises(ValueError, match="object storage"):
        service.get_client(infra)
    del services["s3"]
    with pytest.raises(ValueError, match="object storage"):
        service.get_client(infra)
    service.teardown(None)
    assert service.state == "un-initialized"


def test_tui_form_materializes_connector_configuration():
    from mlox.config import load_all_service_configs
    from mlox.tui.services.setup import ducklake

    values = {
        "postgres_service_uuid": "pg", "storage_service_uuid": "s3",
        "lake_name": "sales", "bucket": "bucket",
    }
    infra = SimpleNamespace(services=lambda: [], filter_by_group=lambda group: [])
    params = ducklake(infra, None).params(values, infra)
    params["${MLOX_USER_HOME}"] = "/tmp"
    config = next(c for c in load_all_service_configs() if c.id == "ducklake-1.1-connector")
    service = config.instantiate_service(params)
    assert isinstance(service, DuckLakeService)
    assert service.postgres_secret_name == service.s3_secret_name == ""
    assert service.data_path == "s3://bucket/ducklake/sales/"
    assert service.metadata_schema == "ducklake_sales"


def test_ducklake_form_offers_only_supported_storage_services():
    from mlox.tui.services.setup import ducklake

    minio = SimpleNamespace(uuid="minio", name="MinIO", service_config_id="minio-release-2025-07-23-docker", capabilities={ServiceCapability.OBJECT_STORAGE, ServiceCapability.S3_OBJECT_STORAGE})
    gcs = SimpleNamespace(uuid="gcs", name="GCS", service_config_id="gcp-storage-0.1.0", capabilities={ServiceCapability.OBJECT_STORAGE})
    infra = SimpleNamespace(services=lambda: [minio, gcs], filter_by_group=lambda group: [])
    field = next(f for f in ducklake(infra, None).fields if f.name == "storage_service_uuid")
    assert [value for _, value in field.options] == ["minio"]


@pytest.mark.parametrize("s3_key", ["s3_connection", "minio_root_credentials"])
def test_accepts_exported_service_secrets(monkeypatch, s3_key):
    conn = FakeConnection()
    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda _: conn))
    c = client()
    c.secret_manager.values["postgres"] = {"postgres_connection": c.secret_manager.values["postgres"]}
    c.secret_manager.values["s3"] = {s3_key: c.secret_manager.values["s3"]}
    assert c.connect() is conn


def test_collect_ducklake_secrets_and_refresh_after_rotation():
    from mlox.application.use_cases.secrets import collect_service_secrets

    manager = SecretManager()
    manager.save_secret = lambda name, value: manager.values.__setitem__(name, value)
    pg = SimpleNamespace(capabilities={ServiceCapability.DATABASE}, service_urls={}, port=5432, db="catalog",
                         get_secrets=lambda: {"postgres_connection": manager.values["postgres"]})
    s3 = SimpleNamespace(capabilities={ServiceCapability.S3_OBJECT_STORAGE}, service_urls={},
                         get_secrets=lambda: {"s3_connection": manager.values["s3"]})
    services = {"pg": pg, "s3": s3, "sm": SimpleNamespace(get_secret_manager=lambda infra: manager)}
    infra = SimpleNamespace(get_service_by_uuid=services.get)
    service = DuckLakeService(name="lake", service_config_id="ducklake-1.1-connector", template="ducklake/mlox.ducklake.yaml", target_path="/tmp/lake", postgres_service_uuid="pg", storage_service_uuid="s3", data_path="s3://bucket/ducklake/sales/", metadata_schema="ducklake_sales", catalog_name="sales")
    service.bind_service_lookup(infra)
    infra.bundles = [SimpleNamespace(services=[service])]
    descriptor = SimpleNamespace(id="embedded", name="Embedded", kind="embedded", service_uuid=None, is_active=True,
                                 is_available=True, supports_keyfile_export=False, manager=manager, service=None)
    workspace = SimpleNamespace(probe_secret_manager=lambda _: descriptor, infrastructure=infra)
    service.setup(None)
    assert service.uuid not in manager.values
    result = collect_service_secrets(workspace, "embedded")
    assert result.success and result.data["service_count"] == 1
    secret = manager.values[service.uuid]
    assert secret["postgres_connection"]["password"] == "pg-secret"
    assert secret["s3_connection"]["password"] == "s3-secret"
    portable = DuckLakeClient.from_secret(manager, service.uuid)
    assert portable.catalog_name == "sales" and portable.data_path == service.data_path
    direct = service.get_client(infra)
    assert direct.postgres_secret_name == service.uuid
    manager.values["postgres"]["password"] = "rotated"
    assert direct.secret_manager.load_secret(service.uuid)["postgres_connection"]["password"] == "rotated"
    assert manager.values[service.uuid]["postgres_connection"]["password"] == "pg-secret"
    assert collect_service_secrets(workspace, "embedded").success
    assert manager.values[service.uuid]["postgres_connection"]["password"] == "rotated"


def test_new_ducklake_setup_requires_no_secret_manager():
    from mlox.tui.services.setup import ducklake
    infra = SimpleNamespace(services=lambda: [], filter_by_group=lambda group: [])
    form = ducklake(infra, None)
    assert "secret_manager_uuid" not in {field.name for field in form.fields}
    params = form.params({"lake_name": "sales", "bucket": "bucket", "postgres_service_uuid": "pg", "storage_service_uuid": "s3"}, infra)
    assert "${SECRET_MANAGER_UUID}" not in params


@pytest.mark.parametrize("name,bucket", [("../sales", "bucket"), ("sales", "../bucket"), ("sales-name", "bucket")])
def test_invalid_derived_lake_names_are_rejected(name, bucket):
    from mlox.tui.services.setup import _ducklake_params
    with pytest.raises(ValueError):
        _ducklake_params({"lake_name": name, "bucket": bucket}, None)


def test_exported_certificates_live_for_connection(monkeypatch):
    from pathlib import Path
    conn = FakeConnection()
    monkeypatch.setitem(sys.modules, "duckdb", SimpleNamespace(connect=lambda _: conn))
    c = client()
    c.secret_manager.values["s3"]["certificate"] = "example certificate"
    with c.connect() as opened:
        path = Path(next(params[0] for sql, params in conn.calls if sql.startswith("SET ca_cert_file")))
        assert path.read_text() == "example certificate"
        assert path.stat().st_mode & 0o777 == 0o600
    assert not path.exists()
