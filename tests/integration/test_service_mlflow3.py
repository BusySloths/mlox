import os
import time
import pytest
import mlflow  # type: ignore
import logging
import pandas as pd

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle
from tests.integration.conftest import wait_for_service_ready

# Mark this module as an integration test
pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


class IdentityModel(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input):
        return model_input


@pytest.fixture(scope="module")
def install_mlflow3_service(ubuntu_docker_server):
    """Install and start the MLflow service on the provided server."""
    # Prepare infrastructure with the existing server
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Load MLflow service configuration
    config = load_config(get_stacks_path(), "/mlflow", "mlox.mlflow.3.8.1.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add MLflow service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
        # Allow some time for containers to become healthy
    wait_for_service_ready(service, bundle, retries=6, interval=20, no_checks=True)

    yield bundle_added, service

    # Teardown after tests
    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception:
            pass
        try:
            service.teardown(conn)
        except Exception:
            pass
    infra.remove_bundle(bundle_added)


def test_mlflow_service_is_running(install_mlflow3_service):
    """Verify MLflow service is reported as running and exposes a URL."""
    bundle, service = install_mlflow3_service
    assert service.service_url
    assert service.state == "running"

    status = wait_for_service_ready(service, bundle, retries=12, interval=30)
    # with bundle.server.get_server_connection() as conn:
    #     status = service.check(conn)
    assert status.get("status") == "running"


def test_mlflow_log_dummy_model(install_mlflow3_service):
    """Log a simple identity model to the MLflow server and verify it can be loaded and used."""
    _, service = install_mlflow3_service

    # Point the client to the server URL
    try:
        mlflow.set_tracking_uri(service.service_url)
        os.environ["MLFLOW_TRACKING_USERNAME"] = service.ui_user
        os.environ["MLFLOW_TRACKING_PASSWORD"] = service.ui_pw
        os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

        # Start a run and log a simple PythonModel that returns input unchanged
        mlflow.set_experiment("test_experiment")
        with mlflow.start_run(run_name="test_run") as run:
            mlflow.pyfunc.log_model("model", python_model=IdentityModel())
            logger.info(f"Logged model in run {run.info.run_id}")
            run_id = mlflow.active_run().info.run_id
            model_uri = f"runs:/{run_id}/model"
        # Load the model back and run a prediction
        loaded = mlflow.pyfunc.load_model(model_uri)
        df = pd.DataFrame({"a": [1, 2, 3]})
        pred = loaded.predict(df)

        # Compare outputs - for DataFrame input, identity model should return same structure
        # Use pandas testing if available, fallback to simple equality
        try:
            pd.testing.assert_frame_equal(
                pred.reset_index(drop=True), df.reset_index(drop=True)
            )
        except Exception:
            assert pred.equals(df)

    except Exception as e:
        pytest.fail(f"Could not log/load model against MLflow server: {e}")
