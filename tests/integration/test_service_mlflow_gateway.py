import logging
import os
import time

import mlflow  # type: ignore
import pandas as pd
import pytest
import requests

from mlox.config import get_stacks_path, load_config
from mlox.infra import Infrastructure
from tests.integration.conftest import wait_for_service_ready
from tests.integration.test_service_mlflow3 import install_mlflow3_service  # noqa: F401

pytestmark = pytest.mark.integration
pytest_plugins = ["tests.integration.test_service_mlflow3"]

logger = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]


class IdentityModel(mlflow.pyfunc.PythonModel):  # type: ignore
    def predict(self, context, model_input, params=None) -> pd.DataFrame:
        return pd.DataFrame(model_input)


def _register_identity_model(service_url: str, username: str, password: str) -> tuple[str, str]:
    mlflow.set_tracking_uri(service_url)
    mlflow.set_registry_uri(service_url)
    os.environ["MLFLOW_TRACKING_USERNAME"] = username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = password
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

    mlflow.set_experiment("test_gateway_experiment")
    with mlflow.start_run(run_name="test_gateway_run") as run:
        model_info = mlflow.pyfunc.log_model("model", python_model=IdentityModel())
        model_uri = f"runs:/{run.info.run_id}/{model_info.artifact_path}"

    model_name = f"gateway_identity_model_{int(time.time())}"
    mv = mlflow.register_model(model_uri, model_name)

    client = mlflow.tracking.MlflowClient()
    for _ in range(30):
        details = client.get_model_version(name=model_name, version=mv.version)
        if details.status == "READY":
            return model_name, str(mv.version)
        time.sleep(2)

    raise RuntimeError("Model version did not become READY in time")


@pytest.fixture(scope="module")
def deploy_mlflow_gateway(ubuntu_docker_server, install_mlflow3_service):
    infra = Infrastructure()
    bundle, mlflow_service = install_mlflow3_service
    infra.bundles.append(bundle)

    mlflow_status = wait_for_service_ready(
        mlflow_service, bundle, retries=12, interval=30
    )
    assert mlflow_status.get("status") == "running"

    model_name, model_version = _register_identity_model(
        mlflow_service.service_url, mlflow_service.ui_user, mlflow_service.ui_pw
    )

    gateway_config = load_config(
        get_stacks_path(), "/mlflow_gateway", "mlox.mlflow_gateway.3.8.1.yaml"
    )
    params = {
        "${TRACKING_URI}": mlflow_service.service_url,
        "${TRACKING_USER}": mlflow_service.ui_user,
        "${TRACKING_PW}": mlflow_service.ui_pw,
        "${GATEWAY_REQUIREMENTS_TXT}": "",
        "${MODEL_REGISTRY_UUID}": mlflow_service.uuid,
    }

    gateway_bundle = infra.add_service(
        ubuntu_docker_server.ip, gateway_config, params=params
    )
    if not gateway_bundle:
        pytest.skip("Failed to add MLflow Gateway service from config")

    gateway_service = gateway_bundle.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        gateway_service.setup(conn)
        gateway_service.spin_up(conn)

    yield gateway_service, gateway_bundle, model_name, model_version

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            gateway_service.spin_down(conn)
        except Exception as exc:
            logger.warning("Error during MLflow Gateway spin_down: %s", exc)
        try:
            gateway_service.teardown(conn)
        except Exception as exc:
            logger.warning("Error during MLflow Gateway teardown: %s", exc)
    infra.remove_bundle(gateway_bundle)


def test_mlflow_gateway_is_ready(deploy_mlflow_gateway):
    gateway_service, bundle, _, _ = deploy_mlflow_gateway
    status = wait_for_service_ready(gateway_service, bundle, retries=30, interval=30)
    assert status.get("status") == "running"


def test_mlflow_gateway_identity_prediction(deploy_mlflow_gateway):
    gateway_service, bundle, model_name, model_version = deploy_mlflow_gateway
    status = wait_for_service_ready(gateway_service, bundle, retries=30, interval=30)
    assert status.get("status") == "running"

    payload = {
        "input_data": [[1.0, 2.0], [3.0, 4.0]],
        "params": {},
        "registry_model_name": model_name,
        "registry_model_version": model_version,
    }
    response = requests.post(
        f"{gateway_service.service_url}/prod/predict",
        json=payload,
        auth=(gateway_service.user, gateway_service.pw),
        headers={"Host": gateway_service.service_url.split("//", 1)[1].split(":", 1)[0]},
        verify=False,
        timeout=120,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"][0]["0"] == 1.0
