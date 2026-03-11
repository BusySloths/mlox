import os
import time
import logging
import urllib.parse
import pytest
import requests
import mlflow  # type: ignore

import pandas as pd
from typing import Dict

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle
from tests.integration.conftest import wait_for_service_ready
from tests.integration.test_service_mlflow3 import install_mlflow3_service  # noqa: F401

pytestmark = pytest.mark.integration
pytest_plugins = ["tests.integration.test_service_mlflow3"]

logger = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]


class IdentityModel(mlflow.pyfunc.PythonModel):  # type: ignore
    def get_conda_env(self) -> Dict:
        return {
            "name": "mlflow-models",
            "channels": ["defaults"],
            "dependencies": [
                f"python={self.requirements_python_version or '3.12.5'}",
                {"pip": [f"mlflow=={mlflow.__version__}"]},
            ],
        }

    def load_context(self, context):
        logger.info("Done.")

    def predict(self, context, model_input, params=None) -> pd.DataFrame:
        return model_input


def _register_identity_model(service_url: str, username: str, password: str) -> str:
    mlflow.set_tracking_uri(service_url)
    mlflow.set_registry_uri(service_url)
    os.environ["MLFLOW_TRACKING_USERNAME"] = username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = password
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

    mlflow.set_experiment("test_experiment")
    with mlflow.start_run(run_name="test_run") as run:
        mlflow.pyfunc.log_model("model", python_model=IdentityModel())
        run_id = run.info.run_id
        model_uri = f"runs:/{run_id}/model"

    model_name = f"identity_model_{int(time.time())}"
    mv = mlflow.register_model(model_uri, model_name)

    client = mlflow.tracking.MlflowClient()
    for _ in range(30):
        details = client.get_model_version(name=model_name, version=mv.version)
        if details.status == "READY":
            return f"{model_name}/{mv.version}"
        time.sleep(2)

    raise RuntimeError("Model version did not become READY in time")


@pytest.fixture(scope="module")
def deploy_mlflow_mlserver(ubuntu_docker_server, install_mlflow3_service):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    bundle, mlflow_service = install_mlflow3_service
    mlflow_status = wait_for_service_ready(
        mlflow_service, bundle, retries=12, interval=30
    )
    assert mlflow_status.get("status") == "running"

    model_name = _register_identity_model(
        mlflow_service.service_url, mlflow_service.ui_user, mlflow_service.ui_pw
    )

    mlserver_config = load_config(
        get_stacks_path(), "/mlflow_mlserver", "mlox.mlserver.3.8.1.yaml"
    )
    params = {
        "${MODEL_NAME}": model_name,
        "${TRACKING_URI}": mlflow_service.service_url,
        "${TRACKING_USER}": mlflow_service.ui_user,
        "${TRACKING_PW}": mlflow_service.ui_pw,
        "${MODEL_REGISTRY_UUID}": mlflow_service.uuid,
    }

    mlserver_bundle = infra.add_service(
        ubuntu_docker_server.ip, mlserver_config, params=params
    )
    if not mlserver_bundle:
        pytest.skip("Failed to add MLServer service from config")

    mlserver_service = mlserver_bundle.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        mlserver_service.setup(conn)
        mlserver_service.spin_up(conn)

    yield mlserver_service, bundle

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            mlserver_service.spin_down(conn)
        except Exception as exc:
            logger.warning("Error during MLServer spin_down: %s", exc)
        try:
            mlserver_service.teardown(conn)
        except Exception as exc:
            logger.warning("Error during MLServer teardown: %s", exc)
    infra.remove_bundle(mlserver_bundle)


def test_mlserver_is_ready(deploy_mlflow_mlserver):
    mlserver_service, bundle = deploy_mlflow_mlserver
    status = wait_for_service_ready(mlserver_service, bundle, retries=30, interval=60)
    assert status.get("status") == "running"


# def test_mlserver_identity_model_inference(deploy_mlflow_mlserver):
#     """Verify the deployed identity model responds with the original input."""
#     mlserver_service, bundle = deploy_mlflow_mlserver

#     status = wait_for_service_ready(mlserver_service, bundle, retries=30, interval=60)
#     assert status.get("status") == "running"

#     invocations_url = f"{mlserver_service.service_url}/invocations"
#     invocations_payload = {
#         "dataframe_split": {
#             "columns": ["a"],
#             "data": [[1.0], [2.0], [3.0]],
#         }
#     }
#     v2_payload = {
#         "inputs": [
#             {
#                 "name": "input-0",
#                 "shape": [3, 1],
#                 "datatype": "FP64",
#                 "data": [[1.0], [2.0], [3.0]],
#             }
#         ]
#     }

#     def _assert_invocations_response(resp: requests.Response) -> None:
#         body = resp.json()
#         predictions = body.get("predictions")
#         assert predictions is not None, body

#         values = None
#         if isinstance(predictions, list) and len(predictions) > 0:
#             if isinstance(predictions[0], dict):
#                 values = [item.get("a") for item in predictions]
#             elif isinstance(predictions[0], list):
#                 values = [row[0] for row in predictions]
#             else:
#                 values = predictions
#         assert values == [1.0, 2.0, 3.0], body

#     def _assert_v2_response(resp: requests.Response) -> None:
#         body = resp.json()
#         assert "outputs" in body
#         assert len(body["outputs"]) > 0
#         output_data = body["outputs"][0].get("data")
#         assert output_data is not None
#         assert output_data == [[1.0], [2.0], [3.0]] or output_data == [1.0, 2.0, 3.0]

#     # Fallback: some deployments expose only V2 model inference routes.
#     candidate_names = ["mlflow-model", getattr(mlserver_service, "model", "")]
#     if "/" in getattr(mlserver_service, "model", ""):
#         candidate_names.append(getattr(mlserver_service, "model", "").split("/", 1)[0])
#     candidate_names = [n for n in dict.fromkeys(candidate_names) if n]

#     retry_count = 20
#     retry_interval_sec = 15
#     attempted_errors = []

#     for attempt in range(retry_count):
#         response = requests.post(
#             invocations_url,
#             json=invocations_payload,
#             verify=False,
#             auth=(mlserver_service.user, mlserver_service.pw),
#             headers={"Host": bundle.server.ip, "Content-Type": "application/json"},
#             timeout=30,
#         )
#         if response.status_code == 200:
#             _assert_invocations_response(response)
#             return

#         current_errors = [
#             f"{invocations_url} -> {response.status_code}: {response.text}"
#         ]

#         for model_name in candidate_names:
#             encoded_name = urllib.parse.quote(model_name, safe="")
#             infer_url = f"{mlserver_service.service_url}/v2/models/{encoded_name}/infer"
#             v2_response = requests.post(
#                 infer_url,
#                 json=v2_payload,
#                 verify=False,
#                 auth=(mlserver_service.user, mlserver_service.pw),
#                 headers={"Host": bundle.server.ip},
#                 timeout=30,
#             )
#             if v2_response.status_code == 200:
#                 _assert_v2_response(v2_response)
#                 return
#             current_errors.append(
#                 f"{infer_url} -> {v2_response.status_code}: {v2_response.text}"
#             )

#         attempted_errors = current_errors
#         if attempt < retry_count - 1:
#             time.sleep(retry_interval_sec)

#     pytest.fail(
#         "Inference failed after warmup retries. Last errors: "
#         + " | ".join(attempted_errors)
#     )
