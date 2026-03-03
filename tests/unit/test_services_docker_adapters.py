from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from urllib.error import HTTPError

from mlox.services.airflow.docker import AirflowDockerService
from mlox.services.influx.docker import InfluxDockerService
from mlox.services.kafka.docker import KafkaDockerService, _generate_cluster_id
from mlox.services.litellm.docker import LiteLLMDockerService
from mlox.services.milvus.docker import MilvusDockerService, _generate_htpasswd_sha1
from mlox.services.minio.docker import MinioDockerService
from mlox.services.mlflow.docker import MLFlowDockerService
from mlox.services.mlflow_mlserver.docker import MLFlowMLServerDockerService
from mlox.services.openbao.client import OpenBaoSecretManager
from mlox.services.openbao.docker import OpenBaoDockerService
from mlox.services.otel.docker import OtelDockerService
from mlox.services.postgres.docker import PostgresDockerService
from mlox.services.redis.docker import RedisDockerService
from mlox.services.registry.docker import RegistryDockerService
from mlox.services.tsm.service import TSMService


BASE = {
    "name": "svc",
    "service_config_id": "cfg",
    "template": "/tmp/compose.yaml",
    "target_path": "/tmp/stack",
}


class FakeExec:
    def __init__(self):
        self.calls = []
        self.files = {}
        self.appended = {}
        self.service_states = {}
        self.all_states = {}
        self.execute_result = "200"
        self.history = [{"action": "boot", "status": "ok"}]
        self.user_id = 1000

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_copy(self, conn, src, dst):
        self._record("fs_copy", src, dst)

    def fs_copy_remote_file(self, conn, src, dst):
        self._record("fs_copy_remote_file", src, dst)

    def tls_setup(self, conn, host, path):
        self._record("tls_setup", host, path)

    def tls_setup_no_config(self, conn, host, path):
        self._record("tls_setup_no_config", host, path)

    def fs_read_file(self, conn, path, format=None):
        self._record("fs_read_file", path, format)
        return self.files.get(path, "CERT")

    def fs_append_line(self, conn, path, line):
        self._record("fs_append_line", path, line)
        self.appended.setdefault(path, []).append(line)

    def fs_create_empty_file(self, conn, path):
        self._record("fs_create_empty_file", path)

    def fs_write_file(self, conn, path, content):
        self._record("fs_write_file", path)
        self.files[path] = content

    def fs_find_and_replace(self, conn, path, old, new):
        self._record("fs_find_and_replace", path, old, new)

    def fs_concatenate_files(self, conn, srcs, dst):
        self._record("fs_concatenate_files", tuple(srcs), dst)

    def fs_set_permissions(self, conn, path, mode, **kwargs):
        self._record("fs_set_permissions", path, mode, kwargs)

    def fs_touch(self, conn, path):
        self._record("fs_touch", path)

    def fs_delete_dir(self, conn, path):
        self._record("fs_delete_dir", path)

    def docker_up(self, conn, compose_path, env_path):
        self._record("docker_up", compose_path, env_path)

    def docker_down(self, conn, *args, **kwargs):
        self._record("docker_down", *args, **kwargs)

    def docker_service_state(self, conn, service_name):
        self._record("docker_service_state", service_name)
        return self.service_states.get(service_name, "stopped")

    def docker_all_service_states(self, conn):
        self._record("docker_all_service_states")
        return self.all_states

    def sys_user_id(self, conn):
        self._record("sys_user_id")
        return self.user_id

    def execute(self, conn, command, group=None, description=""):
        self._record("execute", command, group, description)
        return self.execute_result


@pytest.fixture
def conn():
    return SimpleNamespace(host="example.test")


def _set_exec(service, fake_exec: FakeExec):
    service.exec = fake_exec
    return service


def test_redis_setup_check_and_secrets(conn):
    service = _set_exec(
        RedisDockerService(**BASE, pw="redis-pass", port="6379"),
        FakeExec(),
    )

    service.setup(conn)
    assert service.service_ports["Redis"] == 6379
    assert service.service_urls["Redis"] == "https://example.test:6379"

    service.exec.service_states["redis"] = "running"
    assert service.check(conn) == {"status": "running"}

    secrets = service.get_secrets()["redis_connection"]
    assert secrets["password"] == "redis-pass"
    assert secrets["connection_url"].startswith("rediss://")


def test_postgres_setup_and_secrets_dsn(conn):
    service = _set_exec(
        PostgresDockerService(**BASE, user="pg", pw="pw", db="db", port="5432"),
        FakeExec(),
    )

    service.setup(conn)
    service.exec.service_states["postgres"] = "running"
    assert service.check(conn) == {"status": "running"}

    dsn = service.get_secrets()["postgres_connection"]["dsn"]
    assert dsn == "postgresql://pg:pw@example.test:5432/db"


def test_influx_setup_and_check(conn):
    service = _set_exec(
        InfluxDockerService(**BASE, user="inf", pw="pw", port="8086", token="tok"),
        FakeExec(),
    )

    service.setup(conn)
    assert service.service_urls["InfluxDB"] == "https://example.test:8086"
    assert service.check(conn) == {"status": "stopped"}
    assert service.get_secrets() == {
        "influx_admin_credentials": {"username": "inf", "password": "pw", "token": "tok"}
    }


def test_minio_check_running_and_stopped(conn):
    service = _set_exec(
        MinioDockerService(
            **BASE,
            root_user="minio",
            root_password="secret",
            api_port="9000",
            console_port="9001",
        ),
        FakeExec(),
    )

    service.setup(conn)
    service.exec.all_states = {"proj_minio_1": {"Status": "running"}}
    assert service.check(conn) == {"status": "running"}

    service.exec.all_states = {"proj_other_1": {"Status": "running"}}
    assert service.check(conn) == {"status": "stopped"}


def test_kafka_setup_check_and_helpers(conn):
    cid = _generate_cluster_id()
    assert len(cid) >= 20
    assert "=" not in cid

    service = _set_exec(
        KafkaDockerService(**BASE, ssl_password="sslpw", ssl_port="9093"),
        FakeExec(),
    )

    service.setup(conn)
    assert service.service_url == "ssl://example.test:9093"

    service.exec.all_states = {"kafka": {"Status": "running", "Health": {"Status": "healthy"}}}
    assert service.check(conn)["status"] == "running"

    service.exec.all_states = {}
    assert service.check(conn) == {"status": "stopped"}

    assert service.get_secrets() == {"kafka_ssl_credentials": {"password": "sslpw"}}


def test_registry_setup_check_and_htpasswd(conn):
    service = _set_exec(
        RegistryDockerService(**BASE, username="u", password="p", port="invalid"),
        FakeExec(),
    )

    service.setup(conn)
    assert service.service_ports["Registry"] == 5000
    service.exec.service_states["registry"] = "running"
    assert service.check(conn) == {"status": "running"}

    secret = service.get_secrets()["registry_credentials"]
    assert secret["username"] == "u"

    with pytest.raises(ValueError):
        RegistryDockerService._generate_htpasswd_entry("", "x")


def test_milvus_setup_and_hash_helper(conn):
    entry = _generate_htpasswd_sha1("alice", "pw")
    assert entry.startswith("alice:{SHA}")

    service = _set_exec(
        MilvusDockerService(**BASE, config="milvus.yaml", user="mu", pw="mpw", port="19530"),
        FakeExec(),
    )
    service.setup(conn)

    assert service.service_url == "tcp://example.test:19530"
    assert service.get_secrets() == {
        "milvus_credentials": {"username": "mu", "password": "mpw"}
    }


def test_openbao_setup_spin_check_and_secret_manager(conn):
    service = _set_exec(
        OpenBaoDockerService(**BASE, root_token="root", port="8200", mount_path="kv"),
        FakeExec(),
    )

    service.setup(conn)
    assert service.port == 8200
    assert service.service_url == "https://example.test:8200"

    assert service.spin_up(conn) is True
    assert service.state == "running"

    service.exec.all_states = {service.compose_service_names["OpenBao"]: {"Status": "running"}}
    assert service.check(conn) == {"status": "running"}

    assert service.spin_down(conn) is True
    assert service.state == "stopped"

    infra = SimpleNamespace(
        get_bundle_by_service=lambda _: SimpleNamespace(server=SimpleNamespace(ip="10.0.0.7"))
    )
    sm = service.get_secret_manager(infra)
    assert isinstance(sm, OpenBaoSecretManager)


def test_otel_setup_check_and_read_telemetry(conn):
    service = _set_exec(
        OtelDockerService(
            **BASE,
            relic_endpoint="https://otlp.newrelic.example",
            relic_key="nr-key",
            grafana_cloud_endpoint="https://otlp-gateway-prod-eu-west-2.grafana.net/otlp",
            grafana_cloud_key="Basic abc123",
            config="otel.yaml",
            port_grpc="4317",
            port_http="4318",
            port_health="13133",
        ),
        FakeExec(),
    )

    service.setup(conn)
    assert service.service_ports["OTLP gRPC receiver"] == 4317
    secrets = service.get_secrets()
    assert secrets["otel_client_connection"]["collector_url"] == "https://example.test:4317"
    assert secrets["otel_client_connection"]["trusted_certs"] == "CERT"
    assert secrets["otel_client_connection"]["insecure_tls"] is False
    assert secrets["otel_client_connection"]["protocol"] == "otlp_grpc"

    replacements = [
        call
        for call in service.exec.calls
        if call[0] == "fs_find_and_replace"
        and call[1][0] == "/tmp/stack/otel-collector-config.yaml"
    ]
    assert len(replacements) == 5
    pipeline_replacements = [
        args
        for _, args, _ in replacements
        if args[1]
        in {
            "__TRACES_EXPORTER_LIST__",
            "__METRICS_EXPORTER_LIST__",
            "__LOGS_EXPORTER_LIST__",
        }
    ]
    assert len(pipeline_replacements) == 3
    for args in pipeline_replacements:
        assert args[2] == "debug, file, otlphttp/new_relic, otlphttp/grafana_cloud"
    block_replacements = {args[1]: args[2] for _, args, _ in replacements}
    assert "otlphttp/new_relic" in block_replacements["__NEW_RELIC_EXPORTER_BLOCK__"]
    assert "api-key" in block_replacements["__NEW_RELIC_EXPORTER_BLOCK__"]
    assert "otlphttp/grafana_cloud" in block_replacements["__GRAFANA_CLOUD_EXPORTER_BLOCK__"]
    assert "Authorization" in block_replacements["__GRAFANA_CLOUD_EXPORTER_BLOCK__"]

    service.exec.service_states["otel-collector"] = "created"
    assert service.check(conn)["status"] == "starting"

    @contextmanager
    def _cm():
        yield conn

    service.exec.files["/tmp/stack/otel-data/telemetry.json"] = "{}"
    bundle = SimpleNamespace(server=SimpleNamespace(get_server_connection=lambda: _cm()))
    assert service.get_telemetry_data(bundle) == "{}"


def test_otel_setup_without_relic_keeps_local_exporters(conn):
    service = _set_exec(
        OtelDockerService(
            **BASE,
            relic_endpoint="",
            relic_key="",
            config="otel.yaml",
            port_grpc="4317",
            port_http="4318",
            port_health="13133",
        ),
        FakeExec(),
    )

    service.setup(conn)
    replacements = [
        call
        for call in service.exec.calls
        if call[0] == "fs_find_and_replace"
        and call[1][0] == "/tmp/stack/otel-collector-config.yaml"
    ]
    assert len(replacements) == 5
    pipeline_replacements = [
        args
        for _, args, _ in replacements
        if args[1]
        in {
            "__TRACES_EXPORTER_LIST__",
            "__METRICS_EXPORTER_LIST__",
            "__LOGS_EXPORTER_LIST__",
        }
    ]
    assert len(pipeline_replacements) == 3
    for args in pipeline_replacements:
        assert args[2] == "debug, file"
    block_replacements = {args[1]: args[2] for _, args, _ in replacements}
    assert block_replacements["__NEW_RELIC_EXPORTER_BLOCK__"] == ""
    assert block_replacements["__GRAFANA_CLOUD_EXPORTER_BLOCK__"] == ""


def test_otel_setup_with_grafana_cloud_only(conn):
    service = _set_exec(
        OtelDockerService(
            **BASE,
            relic_endpoint="",
            relic_key="",
            grafana_cloud_endpoint="https://otlp-gateway-prod-eu-west-2.grafana.net/otlp",
            grafana_cloud_key="Basic abc123",
            config="otel.yaml",
            port_grpc="4317",
            port_http="4318",
            port_health="13133",
        ),
        FakeExec(),
    )

    service.setup(conn)
    replacements = [
        call
        for call in service.exec.calls
        if call[0] == "fs_find_and_replace"
        and call[1][0] == "/tmp/stack/otel-collector-config.yaml"
    ]
    assert len(replacements) == 5
    pipeline_replacements = [
        args
        for _, args, _ in replacements
        if args[1]
        in {
            "__TRACES_EXPORTER_LIST__",
            "__METRICS_EXPORTER_LIST__",
            "__LOGS_EXPORTER_LIST__",
        }
    ]
    assert len(pipeline_replacements) == 3
    for args in pipeline_replacements:
        assert args[2] == "debug, file, otlphttp/grafana_cloud"
    block_replacements = {args[1]: args[2] for _, args, _ in replacements}
    assert block_replacements["__NEW_RELIC_EXPORTER_BLOCK__"] == ""
    assert "otlphttp/grafana_cloud" in block_replacements["__GRAFANA_CLOUD_EXPORTER_BLOCK__"]


def test_otel_check_falls_back_to_underscored_name(conn):
    service = _set_exec(
        OtelDockerService(
            **BASE,
            relic_endpoint="",
            relic_key="",
            config="otel.yaml",
            port_grpc="4317",
            port_http="4318",
            port_health="13133",
        ),
        FakeExec(),
    )

    service.exec.service_states["otel_collector"] = "running"
    assert service.check(conn) == {"status": "running", "docker_state": "running"}


def test_otel_setup_normalizes_encoded_grafana_auth_header(conn):
    service = _set_exec(
        OtelDockerService(
            **BASE,
            relic_endpoint="",
            relic_key="",
            grafana_cloud_endpoint="https://otlp-gateway-prod-eu-west-2.grafana.net/otlp",
            grafana_cloud_key='"Basic%20abc123=="',
            config="otel.yaml",
            port_grpc="4317",
            port_http="4318",
            port_health="13133",
        ),
        FakeExec(),
    )

    service.setup(conn)
    env_lines = service.exec.appended.get("/tmp/stack/service.env", [])
    assert "OTEL_GRAFANA_CLOUD_KEY=Basic abc123==" in env_lines


def test_mlflow_setup_check_and_list_models(conn, monkeypatch):
    service = _set_exec(
        MLFlowDockerService(**BASE, ui_user="ml", ui_pw="pw", port="5000"),
        FakeExec(),
    )
    service.setup(conn)

    class _Model:
        def __init__(self, name, version):
            self.name = name
            self.description = ""
            self.version = version
            self.current_stage = "None"
            self.aliases = []
            self.status = "READY"
            self.tags = {}
            self.last_updated_timestamp = 1730000000000
            self.run_id = "run-1"

    class _Client:
        def search_registered_models(self, filter_string="", max_results=10):
            return [1, 2]

        def search_model_versions(self, filter_string="", max_results=250):
            return [_Model("demo", "1")]

    class _Tracking:
        MlflowClient = _Client

    monkeypatch.setattr("mlox.services.mlflow.docker.mlflow.set_registry_uri", lambda *_: None)
    monkeypatch.setattr("mlox.services.mlflow.docker.mlflow.tracking", _Tracking)

    out = service.check(conn)
    assert out["status"] == "running"
    models = service.list_models()
    assert models[0]["Model"] == "demo"


def test_mlflow_mlserver_setup_check_and_is_model(conn):
    service = _set_exec(
        MLFlowMLServerDockerService(
            **BASE,
            dockerfile="Dockerfile",
            port="8080",
            model="my-model/1",
            tracking_uri="https://tracking.example",
            tracking_user="u",
            tracking_pw="p",
            user="api",
            pw="pw",
        ),
        FakeExec(),
    )

    assert service.name.startswith("my-model/1@")
    assert service.target_path.endswith("-8080")

    service.setup(conn)
    service.exec.service_states[service.compose_service_names["MLServer"]] = "running"
    service.exec.execute_result = "200"
    assert service.check(conn) == {"status": "running"}

    service.exec.execute_result = "503"
    assert service.check(conn)["status"] == "unknown"

    service.exec.service_states[service.compose_service_names["MLServer"]] = "exited"
    assert service.check(conn) == {"status": "stopped"}

    assert service.is_model("my-model/1") is True
    service.get_dependent_service_by_name = lambda name: object()
    assert service.is_model("registry:my-model:1") is True
    assert service.is_model("registry:my-model") is False


def test_airflow_setup_and_check(conn, monkeypatch):
    service = _set_exec(
        AirflowDockerService(
            **BASE,
            path_dags="/data/dags",
            path_output="/data/output",
            ui_user="airflow",
            ui_pw="airflowpw",
            port="8080",
            secret_path="team-a",
        ),
        FakeExec(),
    )
    service.setup(conn)
    assert service.service_urls["Airflow UI"] == "https://example.test:8080/team-a"

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{\"version\":\"3.0\"}'

    monkeypatch.setattr("mlox.services.airflow.docker.urllib.request.urlopen", lambda *args, **kwargs: _Resp())
    out = service.check(conn)
    assert out["status"] == "running"
    assert out["version"] == "3.0"


def test_litellm_setup_config_and_check_states(conn):
    service = _set_exec(
        LiteLLMDockerService(
            **BASE,
            ollama_script="entrypoint.sh",
            litellm_config="litellm.yaml",
            ui_user="litellm",
            ui_pw="pw",
            ui_port="8000",
            service_port="4000",
            slack_webhook="https://hooks.slack.test",
            api_key="k",
            openai_key="sk-key",
            ollama_models=["llama3", "llama3", "mistral"],
        ),
        FakeExec(),
    )

    service.setup(conn)
    rendered = service.exec.files["/tmp/stack/litellm-config.yaml"]
    assert "gpt-4o-mini" in rendered
    assert rendered.count("model_name: llama3") == 1
    assert rendered.count("model_name: mistral") == 1

    for compose_name in service.compose_service_names.values():
        service.exec.service_states[compose_name] = "running"
    assert service.check(conn)["status"] == "running"

    # created/restarting yields "starting"
    states = list(service.compose_service_names.values())
    service.exec.service_states[states[0]] = "created"
    assert service.check(conn)["status"] == "starting"


def test_tsm_service_get_secret_manager_paths(monkeypatch):
    class _Tiny:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setattr("mlox.services.tsm.service.TinySecretManager", _Tiny)
    monkeypatch.setattr("mlox.services.tsm.service.dataclass_to_dict", lambda _s: {"ok": 1})

    server = SimpleNamespace(
        uuid="srv-1",
        mlox_user=SimpleNamespace(home="/home/mlox"),
    )
    infra = SimpleNamespace(
        bundles=[SimpleNamespace(server=server)],
        get_server_by_uuid=lambda _uuid: server,
    )

    svc = TSMService(**BASE, pw="vaultpw", server_uuid=None)
    svc.secrets_abs_path = "/secure/secrets"
    sm_abs = svc.get_secret_manager(infra)
    assert sm_abs.kwargs["secrets_abs_path"] == "/secure/secrets"

    svc2 = TSMService(**BASE, pw="vaultpw", server_uuid="srv-1")
    svc2.target_path = "/home/mlox/stacks/demo"
    sm_rel = svc2.get_secret_manager(infra)
    assert sm_rel.args[1] == "/stacks/demo"


def test_openbao_secret_manager_core_paths(monkeypatch):
    manager = OpenBaoSecretManager(address="bao.local/", token="tok", mount_path="/kv/")
    assert manager.address == "http://bao.local"
    assert manager.mount_path == "kv"

    def _request(method, path, **kwargs):
        if method == "GET" and path == "/v1/sys/health":
            return {"initialized": True}
        if method == "GET" and path == "/v1/kv/metadata":
            return {"data": {"keys": ["a/"]}}
        if method == "GET" and path == "/v1/kv/data/a":
            return {"data": {"data": {"x": 1}}}
        if method == "POST" and path.startswith("/v1/auth/token/create"):
            return {"auth": {"client_token": "child-token"}}
        return {}

    monkeypatch.setattr(manager, "_request", _request)
    assert manager.is_working() is True
    assert manager.list_secrets(keys_only=False) == {"a": {"x": 1}}
    manager.save_secret("x", "{\"y\":1}")
    assert manager.create_token(300)["client_token"] == "child-token"
    assert manager.get_access_secrets()["mount_path"] == "kv"

    def _raise_404(method, path, **kwargs):
        raise HTTPError(url="http://bao", code=404, msg="not found", hdrs=None, fp=None)

    monkeypatch.setattr(manager, "_request", _raise_404)
    assert manager.load_secret("missing") is None
