"""Run with python -m examples.tracking.mlflow_tracking_example; see examples/README.md."""
import logging
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd

from examples.runtime import setup_runtime
from mlox.services.mlflow.mlops import DeployableModel, MLFlowDeployableModelService

logger = logging.getLogger(__name__)


class MyTrackedModel(DeployableModel):
    """Deterministic normalization, PCA and linear regression."""

    def tracked_training(self, params=None):
        x = np.random.default_rng(42).normal(size=(128, 3))
        y = x @ np.array([1.0, 2.0, -0.5])
        self.mean, self.scale = x.mean(axis=0), x.std(axis=0)
        normalized = (x - self.mean) / self.scale
        _, _, axes = np.linalg.svd(normalized, full_matrices=False)
        self.components = axes.T
        self.weights = np.linalg.lstsq(normalized @ self.components, y, rcond=None)[0]
        mlflow.log_param("training_seed", 42)
        return None

    def live_predict(self, model_input, params=None, artifacts=None):
        logger.info("Model runtime: telemetry=%s, secret_manager=%s",
                    self.get_telemetry_client() is not None,
                    self.get_secret_manager() is not None)
        with self.model_step("pipeline"):
            with self.model_step("input.normalize") as step:
                x = np.atleast_2d(np.asarray(model_input, dtype=float))
                step.observe_array("input", x)
                normalized = (x - self.mean) / self.scale
                step.observe_array("output", normalized)
            with self.model_step("pca.transform", component="PCA", component_version="1") as step:
                transformed = normalized @ self.components
                step.observe_array("output", transformed)
            with self.model_step("regression.predict", component="LR") as step:
                prediction = transformed @ self.weights
                step.observe_array("output", prediction)
        return pd.DataFrame({"prediction": prediction})


def tracked_experiment():
    client, _ = setup_runtime(tracking=True)
    try:
        root = Path(__file__).resolve().parents[2]
        service = MLFlowDeployableModelService(
            MyTrackedModel(), "mlox-pca-regression-example",
            code_paths=[str(root / "mlox"), str(root / "examples")],
        )
        inputs = np.array([[1.0, 2.0, 3.0], [3.0, 2.0, 1.0]])
        info = service.track_model(input_example=inputs)
        loaded = mlflow.pyfunc.load_model(info.model_uri)
        print(loaded.predict(inputs))
        logger.info("Tracked model and completed inference: %s", info.model_uri)
    finally:
        if client:
            client.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracked_experiment()
