from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from mlox.config import load_all_service_configs
from mlox.executors import TaskGroup
from mlox.service import ServiceCapability
from mlox.services.mlflow_gateway.k3s import MLFlowGatewayK3sService
from mlox.view.services import _STREAMLIT_SERVICE_BINDINGS


class FakeExecutor:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.calls: list[tuple] = []
        self.apply_result = "configured"
        self.rollout_result = "deployment successfully rolled out"
        self.ready_result = "1"
        self.health_result = "200"

    def _record(self, name, *args, **kwargs) -> None:
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path: str) -> None:
        self._record("fs_create_dir", path)

    def fs_write_file(self, conn, path: str, content: str) -> None:
        self._record("fs_write_file", path, content)
        self.files[path] = content

    def fs_delete_dir(self, conn, path: str) -> None:
        self._record("fs_delete_dir", path)

    def k8s_apply_manifest(self, conn, path: str, **kwargs):
        self._record("k8s_apply_manifest", path, **kwargs)
        return self.apply_result

    def execute(self, conn, command: str, **kwargs):
        self._record("execute", command, **kwargs)
        if "rollout status" in command:
            return self.rollout_result
        if "get deployment/" in command:
            return self.ready_result
        if command.startswith("curl "):
            return self.health_result
        raise AssertionError(f"Unexpected command: {command}")

    def k8s_delete_resource(self, conn, *args, **kwargs):
        self._record("k8s_delete_resource", *args, **kwargs)
        return "namespace deleted"

    def k8s_resource_log_tail(self, conn, resource: str, **kwargs):
        self._record("k8s_resource_log_tail", resource, **kwargs)
        return "gateway log line"


@pytest.fixture
def gateway(tmp_path: Path) -> MLFlowGatewayK3sService:
    serve_script = tmp_path / "serve.py"
    serve_script.write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    service = MLFlowGatewayK3sService(
        name="MLflow Gateway",
        service_config_id="mlflow-gateway-3.8.1-k3s",
        template="/tmp/mlflow-gateway-k3s.yaml",
        target_path="/tmp/mlflow-gateway",
        dockerfile="/tmp/Dockerfile",
        serve_script=str(serve_script),
        start_script="/tmp/start_gateway.sh",
        port=30433,
        tracking_uri="https://mlflow.example:5043",
        tracking_user="tracking-user",
        tracking_pw="tracking-password",
        requirements_txt="xgboost==2.1.0",
        cache_max_models="5",
        cache_ttl_days="6",
        user="gateway-user",
        pw="gateway-password",
    )
    service.exec = FakeExecutor()
    return service


def test_renders_gateway_manifest(gateway: MLFlowGatewayK3sService) -> None:
    manifest = gateway._render_gateway_manifest()

    assert "kind: ConfigMap" in manifest
    assert "from fastapi import FastAPI" in manifest
    assert "xgboost==2.1.0" in manifest
    assert "kind: Secret" in manifest
    assert "name: mlflow-gateway-basic-auth" in manifest
    assert "gateway-user:$apr1$" in manifest
    assert 'gateway-user: "gateway-user"' in manifest
    assert 'gateway-password: "gateway-password"' in manifest
    assert 'tracking-password: "tracking-password"' in manifest
    assert "replicas: 1" in manifest
    assert "image: python:3.12-slim" in manifest
    assert "startupProbe:" in manifest
    assert manifest.count("path: /health") == 3
    assert "name: MLOX_GATEWAY_CACHE_MAX_MODELS" in manifest
    assert 'value: "5"' in manifest
    assert "name: MLOX_GATEWAY_CACHE_TTL_DAYS" in manifest
    assert 'value: "6"' in manifest
    assert "type: ClusterIP" in manifest
    assert "containerPort: 8080" in manifest
    assert "kind: Middleware" in manifest
    assert "basicAuth:" in manifest
    assert "stripPrefix:" in manifest
    assert f'path: "{gateway.ingress_path}"' in manifest
    assert "kind: Ingress" in manifest
    assert "router.entrypoints: websecure" in manifest
    assert 'router.tls: "true"' in manifest
    assert "@kubernetescrd" in manifest
    assert len(list(yaml.safe_load_all(manifest))) == 9


def test_renders_ingress_with_path_middlewares(
    gateway: MLFlowGatewayK3sService,
) -> None:
    manifest = gateway._render_gateway_manifest()

    assert f"name: {gateway.ingress_name}" in manifest
    assert f"namespace: {gateway.namespace}" in manifest
    assert f'path: "{gateway.ingress_path}"' in manifest
    assert f"name: {gateway.service_name}" in manifest
    assert "number: 8080" in manifest
    assert (
        "traefik.ingress.kubernetes.io/router.middlewares: "
        f"{gateway.namespace}-{gateway.basic_auth_middleware}@kubernetescrd,"
        f"{gateway.namespace}-{gateway.strip_prefix_middleware}@kubernetescrd"
    ) in manifest


def test_multiple_gateways_get_distinct_kubernetes_identities(tmp_path: Path) -> None:
    serve_script = tmp_path / "serve.py"
    serve_script.write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    common = {
        "name": "MLflow Gateway",
        "service_config_id": "mlflow-gateway-3.8.1-k3s",
        "template": "/tmp/mlflow-gateway-k3s.yaml",
        "target_path": "/tmp/mlflow-gateway",
        "dockerfile": "/tmp/Dockerfile",
        "serve_script": str(serve_script),
        "start_script": "/tmp/start_gateway.sh",
        "port": 30433,
        "tracking_uri": "https://mlflow.example:5043",
        "tracking_user": "tracking-user",
        "tracking_pw": "tracking-password",
    }

    first = MLFlowGatewayK3sService(**common)
    second = MLFlowGatewayK3sService(**common)

    assert first.gateway_id
    assert second.gateway_id
    assert first.namespace.startswith("mlflow-gateway-")
    assert second.namespace.startswith("mlflow-gateway-")
    assert first.namespace != second.namespace
    assert first.ingress_path != second.ingress_path


def test_setup_applies_manifest_and_publishes_path_url(
    gateway: MLFlowGatewayK3sService,
) -> None:
    conn = SimpleNamespace(host="gateway.example")

    gateway.setup(conn)

    assert gateway.manifest_path in gateway.exec.files
    rollout = next(
        call
        for call in gateway.exec.calls
        if call[0] == "execute" and "rollout status" in call[1][0]
    )
    assert rollout[2]["group"] == TaskGroup.KUBERNETES
    assert not any(call[0].startswith("helm_") for call in gateway.exec.calls)
    assert gateway.service_url == f"https://gateway.example{gateway.ingress_path}"
    assert gateway.service_ports == {"MLflow Gateway REST API": 443}
    assert gateway.state == "running"


def test_setup_apply_failure_marks_unknown(
    gateway: MLFlowGatewayK3sService,
) -> None:
    gateway.exec.apply_result = None

    gateway.setup(SimpleNamespace(host="gateway.example"))

    assert gateway.state == "unknown"
    assert not any(call[0].startswith("helm_") for call in gateway.exec.calls)


def test_setup_rollout_timeout_keeps_gateway_starting(
    gateway: MLFlowGatewayK3sService,
) -> None:
    gateway.exec.rollout_result = None

    gateway.setup(SimpleNamespace(host="gateway.example"))

    assert gateway.state == "running"
    assert gateway.service_url == f"https://gateway.example{gateway.ingress_path}"


def test_check_uses_deployment_and_authenticated_health(
    gateway: MLFlowGatewayK3sService,
) -> None:
    conn = SimpleNamespace(host="gateway.example")
    gateway.service_url = f"https://gateway.example{gateway.ingress_path}"

    assert gateway.check(conn) == {"status": "running"}
    curl = next(
        call[1][0]
        for call in gateway.exec.calls
        if call[0] == "execute" and call[1][0].startswith("curl ")
    )
    assert "--insecure" in curl
    assert "--user gateway-user:gateway-password" in curl
    assert curl.endswith(f"https://gateway.example{gateway.ingress_path}/health")

    gateway.exec.ready_result = ""
    assert gateway.check(conn)["status"] == "starting"
    assert gateway.state == "running"


def test_get_health_normalizes_gateway_readiness(
    gateway: MLFlowGatewayK3sService,
) -> None:
    conn = SimpleNamespace(host="gateway.example")
    gateway.service_url = f"https://gateway.example{gateway.ingress_path}"

    assert ServiceCapability.HEALTH in gateway.capabilities
    health = gateway.get_health(conn)

    assert health["status"] == "running"
    assert health["state"] == "running"
    assert health["healthy"] is True

    gateway.exec.ready_result = ""
    health = gateway.get_health(conn)
    assert health["status"] == "starting"
    assert health["state"] == "starting"
    assert health["healthy"] is False
    assert health["ready_replicas"] == "0"


def test_fetches_gateway_kubernetes_logs(gateway: MLFlowGatewayK3sService) -> None:
    logs = gateway.service_log_tail(object(), tail=25)

    assert gateway.log_labels() == ["MLflow Gateway"]
    assert logs == "gateway log line"
    call = next(
        call for call in gateway.exec.calls if call[0] == "k8s_resource_log_tail"
    )
    assert call[1][0] == "deployment/mlflow-gateway"
    assert call[2]["namespace"] == gateway.namespace
    assert call[2]["tail"] == 25
    assert call[2]["container"] == "gateway"
    assert (
        gateway.service_log_tail(object(), label="missing")
        == "Log label missing not found"
    )


def test_teardown_is_non_blocking_and_clears_service_state(
    gateway: MLFlowGatewayK3sService,
) -> None:
    gateway.service_url = f"https://gateway.example{gateway.ingress_path}"
    gateway.service_urls["MLflow Gateway REST API"] = gateway.service_url
    gateway.service_ports["MLflow Gateway REST API"] = 443
    gateway.state = "running"

    gateway.teardown(SimpleNamespace(host="gateway.example"))

    delete = next(
        call for call in gateway.exec.calls if call[0] == "k8s_delete_resource"
    )
    assert not any(call[0].startswith("helm_") for call in gateway.exec.calls)
    assert delete[2]["extra_args"] == [
        "--wait=false",
        "--request-timeout=120s",
    ]
    assert any(call[0] == "fs_delete_dir" for call in gateway.exec.calls)
    assert gateway.service_url == ""
    assert gateway.service_urls == {}
    assert gateway.state == "un-initialized"


def test_reuses_gateway_secrets_and_model_validation(
    gateway: MLFlowGatewayK3sService,
) -> None:
    assert gateway.get_secrets() == {
        "mlflow_gateway_basic_auth": {
            "username": "gateway-user",
            "password": "gateway-password",
            "service_url": "",
        },
        "mlflow_tracking_credentials": {
            "username": "tracking-user",
            "password": "tracking-password",
            "tracking_uri": "https://mlflow.example:5043",
            "cache_max_models": "5",
            "cache_ttl_days": "6",
        },
    }
    assert not gateway.is_model("registered-model")


def test_catalog_and_streamlit_handlers_are_registered() -> None:
    configs = {config.id: config for config in load_all_service_configs()}
    config = configs["mlflow-gateway-3.8.1-k3s"]

    assert config.capabilities["backend"] == ["kubernetes"]
    assert config.capabilities["service"] == ["model_server", "health"]
    assert (
        config.build.class_name
        == "mlox.services.mlflow_gateway.k3s.MLFlowGatewayK3sService"
    )
    service = config.instantiate_service(
        {
            "${MLOX_STACKS_PATH}": str(Path(__file__).parents[3] / "mlox" / "services"),
            "${MLOX_USER_HOME}": "/tmp/mlox",
            "${MLOX_AUTO_PORT_REST}": 30433,
            "${TRACKING_URI}": "https://mlflow.example",
            "${TRACKING_USER}": "tracking-user",
            "${TRACKING_PW}": "tracking-password",
            "${GATEWAY_REQUIREMENTS_TXT}": "",
            "${GATEWAY_CACHE_MAX_MODELS}": "10",
            "${GATEWAY_CACHE_TTL_DAYS}": "10",
            "${MLOX_AUTO_USER}": "gateway-user",
            "${MLOX_AUTO_PW}": "gateway-password",
            "${MODEL_REGISTRY_UUID}": "",
        }
    )
    assert isinstance(service, MLFlowGatewayK3sService)
    assert service.namespace.startswith("mlflow-gateway-")
    assert service.ingress_path.startswith("/gateway-")
    binding = _STREAMLIT_SERVICE_BINDINGS["mlox.view.services.mlflow_gateway"]
    assert "mlflow-gateway-3.8.1-k3s" in binding["config_ids"]
    assert binding["function_names"] == ("settings", "setup")
