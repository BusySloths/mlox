from types import SimpleNamespace

from mlox.services.airflow.docker import AirflowDockerService
from mlox.services.ducklake.service import DuckLakeService
from mlox.services.minio.docker import MinioDockerService
from mlox.services.postgres.docker import PostgresDockerService
from mlox.tunnel import TunnelBinding


def test_direct_and_composite_tunnel_plans_preserve_remote_secrets():
    common = dict(service_config_id="test", template="x", target_path="/tmp/test")
    pg = PostgresDockerService(name="pg", user="user", pw="pg-secret", db="db", port=5432, **common)
    s3 = MinioDockerService(name="minio", root_user="key", root_password="s3-secret", api_port=9000, console_port=9001, **common)
    airflow = AirflowDockerService(name="airflow", path_dags="/tmp/dags", path_output="/tmp/output", ui_user="user", ui_pw="airflow-secret", port="1099", **common)
    pg.service_urls["Postgres IP"] = "192.0.2.10"
    s3.service_url = "https://192.0.2.20:9000"
    lake = DuckLakeService(name="lake", postgres_service_uuid=pg.uuid, storage_service_uuid=s3.uuid, data_path="s3://bucket/lake/", **common)
    services = {pg.uuid: pg, s3.uuid: s3}
    hosts = {pg.uuid: SimpleNamespace(uuid="host-1", ip="192.0.2.10"),
             s3.uuid: SimpleNamespace(uuid="host-2", ip="192.0.2.20"),
             airflow.uuid: SimpleNamespace(uuid="host-1", ip="192.0.2.10")}
    infra = SimpleNamespace(get_service_by_uuid=services.get,
                            get_bundle_by_service=lambda service: SimpleNamespace(server=hosts[service.uuid]))
    original_pg, original_s3 = pg.get_secrets(), s3.get_secrets()
    plan = lake.tunnel_plan(infra)
    assert {endpoint.server_uuid for endpoint in plan.endpoints} == {"host-1", "host-2"}
    assert [endpoint.name for endpoint in s3.tunnel_plan(infra).endpoints] == ["MinIO API", "MinIO Console"]
    minio_bindings = tuple(TunnelBinding(endpoint, 19000 + index) for index, endpoint in enumerate(s3.tunnel_plan(infra).endpoints))
    assert s3.tunnel_secrets(infra, minio_bindings)["minio_root_credentials"]["console_url"] == "https://127.0.0.1:19001"
    assert [endpoint.name for endpoint in plan.endpoints] == ["Postgres", "MinIO API"]
    bindings = tuple(TunnelBinding(endpoint, 15432 if endpoint.service_uuid == pg.uuid else 19000) for endpoint in plan.endpoints)
    local = lake.tunnel_secrets(infra, bindings)
    assert local["postgres_connection"]["host"] == "127.0.0.1"
    assert local["postgres_connection"]["port"] == "15432"
    assert local["postgres_connection"]["password"] == "pg-secret"
    assert "dsn" not in local["postgres_connection"]
    assert local["s3_connection"]["endpoint"] == "https://127.0.0.1:19000"
    assert local["s3_connection"]["password"] == "s3-secret"
    assert pg.get_secrets() == original_pg and s3.get_secrets() == original_s3
    airflow_binding = TunnelBinding(airflow.tunnel_plan(infra).endpoints[0], 11099)
    assert airflow.tunnel_secrets(infra, (airflow_binding,))["airflow_ui_credentials"]["base_url"] == "https://127.0.0.1:11099"


def test_airflow_tunnel_health_uses_local_url_without_changing_service(monkeypatch):
    service = AirflowDockerService(name="airflow", service_config_id="test", template="x", target_path="/tmp/test", path_dags="/tmp/dags", path_output="/tmp/output", ui_user="user", ui_pw="password", port="1099")
    service.service_urls["Airflow UI"] = "https://remote:1099"
    infra = SimpleNamespace(get_bundle_by_service=lambda _: SimpleNamespace(server=SimpleNamespace(uuid="s", ip="remote")))
    binding = TunnelBinding(service.tunnel_plan(infra).endpoints[0], 12345)
    seen = []
    def check(self, conn):
        seen.append(self.service_urls["Airflow UI"])
        return {"status": "running"}
    monkeypatch.setattr(AirflowDockerService, "check", check)
    assert service.tunnel_health(infra, (binding,))["healthy"] is True
    assert seen == ["https://127.0.0.1:12345"]
    assert service.service_urls["Airflow UI"] == "https://remote:1099"
