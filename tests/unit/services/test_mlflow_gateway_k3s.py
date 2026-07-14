from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from mlox.config import load_all_service_configs
from mlox.executors import TaskGroup
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
        self.repo_result = "repository added"
        self.helm_install_result = "release installed"

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

    def helm_repo_add(self, conn, *args, **kwargs):
        self._record("helm_repo_add", *args, **kwargs)
        return self.repo_result

    def helm_upgrade_install(self, conn, **kwargs):
        self._record("helm_upgrade_install", **kwargs)
        return self.helm_install_result

    def helm_uninstall(self, conn, **kwargs):
        self._record("helm_uninstall", **kwargs)
        return "release uninstalled"

    def k8s_delete_resource(self, conn, *args, **kwargs):
        self._record("k8s_delete_resource", *args, **kwargs)
        return "namespace deleted"


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
    assert len(list(yaml.safe_load_all(manifest))) == 5


def test_renders_dedicated_traefik_values(
    gateway: MLFlowGatewayK3sService,
) -> None:
    values = gateway._render_traefik_values()

    assert "kubernetesCRD:\n    enabled: false" in values
    assert "kubernetesIngress:\n    enabled: false" in values
    assert "PathPrefix(`/`)" in values
    assert "basicAuth:" in values
    assert "gateway-user:$apr1$" in values
    assert f"mlflow-gateway.{gateway.namespace}.svc.cluster.local:8080" in values
    assert "exposedPort: 30433" in values
    assert "type: LoadBalancer" in values


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

    assert first.namespace.startswith("mlflow-gateway-30433-")
    assert second.namespace.startswith("mlflow-gateway-30433-")
    assert first.namespace != second.namespace
    assert first.traefik_release != second.traefik_release


def test_setup_applies_rolls_out_and_installs_traefik(
    gateway: MLFlowGatewayK3sService,
) -> None:
    conn = SimpleNamespace(host="gateway.example")

    gateway.setup(conn)

    assert gateway.manifest_path in gateway.exec.files
    assert gateway.traefik_values_path in gateway.exec.files
    rollout = next(
        call
        for call in gateway.exec.calls
        if call[0] == "execute" and "rollout status" in call[1][0]
    )
    assert rollout[2]["group"] == TaskGroup.KUBERNETES
    install = next(
        call for call in gateway.exec.calls if call[0] == "helm_upgrade_install"
    )
    assert install[2]["release"] == gateway.traefik_release
    assert install[2]["namespace"] == gateway.namespace
    assert install[2]["extra_args"] == [
        "--version",
        "34.4.1",
        "--values",
        gateway.traefik_values_path,
        "--wait",
        "--timeout",
        "5m",
    ]
    assert gateway.service_url == "https://gateway.example:30433"
    assert gateway.service_ports == {"MLflow Gateway REST API": 30433}
    assert gateway.state == "running"


@pytest.mark.parametrize(
    ("failure", "expected_helm_installs"),
    [
        ("apply", 0),
        ("traefik", 1),
    ],
)
def test_setup_failure_paths(
    gateway: MLFlowGatewayK3sService,
    failure: str,
    expected_helm_installs: int,
) -> None:
    if failure == "apply":
        gateway.exec.apply_result = None
    else:
        gateway.exec.helm_install_result = None

    gateway.setup(SimpleNamespace(host="gateway.example"))

    assert gateway.state == "unknown"
    installs = [
        call for call in gateway.exec.calls if call[0] == "helm_upgrade_install"
    ]
    assert len(installs) == expected_helm_installs


def test_setup_rollout_timeout_keeps_gateway_starting(
    gateway: MLFlowGatewayK3sService,
) -> None:
    gateway.exec.rollout_result = None

    gateway.setup(SimpleNamespace(host="gateway.example"))

    assert gateway.state == "running"
    assert any(call[0] == "helm_upgrade_install" for call in gateway.exec.calls)
    assert gateway.service_url == "https://gateway.example:30433"


def test_check_uses_deployment_and_authenticated_health(
    gateway: MLFlowGatewayK3sService,
) -> None:
    conn = SimpleNamespace(host="gateway.example")
    gateway.service_url = "https://gateway.example:30433"

    assert gateway.check(conn) == {"status": "running"}
    curl = next(
        call[1][0]
        for call in gateway.exec.calls
        if call[0] == "execute" and call[1][0].startswith("curl ")
    )
    assert "--insecure" in curl
    assert "--user gateway-user:gateway-password" in curl
    assert curl.endswith("https://gateway.example:30433/health")

    gateway.exec.ready_result = ""
    assert gateway.check(conn)["status"] == "starting"
    assert gateway.state == "running"


def test_teardown_is_non_blocking_and_clears_service_state(
    gateway: MLFlowGatewayK3sService,
) -> None:
    gateway.service_url = "https://gateway.example:30433"
    gateway.service_urls["MLflow Gateway REST API"] = gateway.service_url
    gateway.service_ports["MLflow Gateway REST API"] = 30433
    gateway.state = "running"

    gateway.teardown(SimpleNamespace(host="gateway.example"))

    uninstall = next(call for call in gateway.exec.calls if call[0] == "helm_uninstall")
    delete = next(
        call for call in gateway.exec.calls if call[0] == "k8s_delete_resource"
    )
    assert uninstall[2]["extra_args"] == ["--timeout=120s"]
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
    assert config.capabilities["service"] == ["model_server"]
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
    assert service.namespace.startswith("mlflow-gateway-30433-")
    binding = _STREAMLIT_SERVICE_BINDINGS["mlox.view.services.mlflow_gateway"]
    assert "mlflow-gateway-3.8.1-k3s" in binding["config_ids"]
    assert binding["function_names"] == ("settings", "setup")
