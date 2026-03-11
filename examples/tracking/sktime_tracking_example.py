"""Educational example: track and optionally register a simple ``sktime`` model in MLflow.

Aim of this example:
- Show the minimum pattern to train a time-series model with ``sktime``.
- Track training params/metrics/data in MLflow.
- Optionally register the model in the MLflow Model Registry.

Registration behavior:
- ``tracked_experiment`` is a string.
- If it is non-empty, the model is registered under that name.
- If it is empty, only experiment tracking is performed.

Credentials:
Load a MLOX project (via env ``MLOX_PROJECT_NAME`` and ``MLOX_PROJECT_PASSWORD``) and extract credentials
from a running MLflow service.
"""

from __future__ import annotations

import os
import mlflow  # type: ignore[import]
import logging
import numpy as np
import pandas as pd  # type: ignore[import]

from pathlib import Path
from typing import Dict

from sktime.datasets import load_airline  # type: ignore[import]
from sktime.forecasting.base import ForecastingHorizon  # type: ignore[import]
from sktime.forecasting.model_selection import temporal_train_test_split  # type: ignore[import]
from sktime.forecasting.naive import NaiveForecaster  # type: ignore[import]
from sktime.performance_metrics.forecasting import mean_absolute_error  # type: ignore[import]

from mlox.services.mlflow.mlops import DeployableModel, MLFlowDeployableModelService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SktimeTrackedModel(DeployableModel):
    """Very small forecasting model wrapper used by ``MLFlowDeployableModelService``."""

    forecaster: NaiveForecaster | None = None

    def live_predict(
        self,
        model_input: np.ndarray | pd.DataFrame,
        params: Dict | None = None,
        artifacts: Dict | None = None,
    ) -> pd.DataFrame:
        if self.forecaster is None:
            raise RuntimeError("Model was not trained yet. Run tracked_training first.")

        raw = 12  # default forecast horizon steps
        if isinstance(model_input, pd.DataFrame) and not model_input.empty:
            raw = model_input.iloc[0, 0]
        elif isinstance(model_input, np.ndarray) and model_input.size > 0:
            raw = model_input.reshape(-1)[0]

        horizon_steps = int(raw)
        fh = ForecastingHorizon(np.arange(1, horizon_steps + 1), is_relative=True)
        y_pred = self.forecaster.predict(fh=fh)

        return pd.DataFrame(
            {
                "forecast_step": np.arange(1, horizon_steps + 1),
                "forecast_value": y_pred.to_numpy(),
            }
        )

    def tracked_training(self, params: Dict | None = None) -> Dict | None:
        params = params or {}
        strategy = str(params.get("strategy", "last"))
        seasonal_period = int(params.get("seasonal_period", 12))
        test_size = int(params.get("test_size", 12))

        # 1) Load a small built-in monthly dataset for an educational, reproducible demo.
        y = load_airline().astype(float)
        y_train, y_test = temporal_train_test_split(y, test_size=test_size)

        # 2) Train a minimal sktime forecaster.
        self.forecaster = NaiveForecaster(strategy=strategy, sp=seasonal_period)
        self.forecaster.fit(y_train)

        # 3) Evaluate and log metrics in MLflow.
        fh = ForecastingHorizon(y_test.index, is_relative=False)
        y_pred = self.forecaster.predict(fh=fh)
        mae = float(mean_absolute_error(y_test, y_pred))

        mlflow.log_params(
            {
                "model_family": "sktime.NaiveForecaster",
                "strategy": strategy,
                "seasonal_period": seasonal_period,
                "test_size": test_size,
            }
        )
        mlflow.log_metric("mae", mae)

        # 4) Log training/evaluation data to make lineage explicit in the run.
        training_df = y_train.to_frame(name="y")
        eval_df = pd.DataFrame(
            {"y_true": y_test.to_numpy(), "y_pred": y_pred.to_numpy()}
        )
        mlflow.log_input(mlflow.data.from_pandas(training_df), context="training")  # type: ignore
        mlflow.log_input(mlflow.data.from_pandas(eval_df), context="evaluation")  # type: ignore

        mlflow.set_tag("example", "sktime_tracking")
        mlflow.set_tag("dataset", "airline")

        return {"README.md": "./README.md"}


def setup_tracker(tracker_service_name: str) -> None:
    """Configure MLflow environment variables."""
    from examples.load_project_data import load_mlox_session

    session = load_mlox_session()
    candidates = session.infra.filter_by_group("experiment-tracking")
    mlflow_service = next(
        (s for s in candidates if s.name == tracker_service_name), None
    )
    if mlflow_service is None:
        raise RuntimeError(f"Could not find MLflow service {tracker_service_name}. ")
    secrets = mlflow_service.get_secrets()
    os.environ["MLFLOW_URI"] = str(secrets.get("service_url", ""))
    os.environ["MLFLOW_TRACKING_USERNAME"] = str(secrets.get("username", ""))
    os.environ["MLFLOW_TRACKING_PASSWORD"] = str(secrets.get("password", ""))
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = str(
        secrets.get("insecure_tls", "true")
    )


def run_sktime_tracking_example(tracked_experiment: str) -> None:
    """Run training + tracking, and optionally register the model.

    Args:
        tracked_experiment: MLflow registered model name.
            - non-empty: register model under this name.
            - empty: skip registration and only track the run.
    """
    model = SktimeTrackedModel()
    repo_root = Path(__file__).resolve().parents[2]

    mlops = MLFlowDeployableModelService(
        model=model,
        model_class="sktime-naive-forecaster",
        code_paths=[str(repo_root / "mlox"), str(repo_root / "examples")],
        requirements_file="examples/tracking/requirements_sktime_mlflow.txt",
    )

    if tracked_experiment:
        mlops.set_registered_model_name(tracked_experiment)
        logger.info("Model will be registered as '%s'.", tracked_experiment)
    else:
        logger.info("tracked_experiment is empty -> skipping model registration.")

    mlops.track_model(
        params={"strategy": "last", "seasonal_period": 12, "test_size": 12},
        input_example=np.array([[12]]),  # predict 12 future steps
        inference_params={"forecast_horizon_steps": 12},
    )

    print("Tracking run completed.")
    if tracked_experiment:
        print(f"Model registration requested under name: {tracked_experiment}")
    else:
        print("Model was tracked only (no registration).")


if __name__ == "__main__":
    setup_tracker(tracker_service_name="mlflow-3.8.1")
    run_sktime_tracking_example(tracked_experiment="sktime-airline-forecaster")
