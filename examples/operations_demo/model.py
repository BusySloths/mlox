"""Instrumented normalization, PCA, regression, and quality-evaluation model."""

from __future__ import annotations

import mlflow
import numpy as np
import pandas as pd

from mlox.services.mlflow.mlops import DeployableModel


MODEL_NAME = "mlox-operations-demo"
FEATURE_COLUMNS = ("feature_1", "feature_2", "feature_3")
TARGET_COLUMN = "target"


def demonstration_batch(rows: int = 64) -> pd.DataFrame:
    """Return the same labelled batch so baseline changes come only from the fault."""

    features = np.random.default_rng(2026).normal(size=(rows, len(FEATURE_COLUMNS)))
    target = features @ np.array([1.25, -2.0, 0.75]) + 0.15
    frame = pd.DataFrame(features, columns=FEATURE_COLUMNS)
    frame[TARGET_COLUMN] = target
    return frame


class OperationsDemoModel(DeployableModel):
    """A deterministic pipeline with an intentionally injectable PCA failure."""

    def tracked_training(self, params=None):
        training = demonstration_batch(512)
        features = training.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
        target = training[TARGET_COLUMN].to_numpy(dtype=float)
        self.mean = features.mean(axis=0)
        self.scale = features.std(axis=0)
        normalized = (features - self.mean) / self.scale
        _, _, axes = np.linalg.svd(normalized, full_matrices=False)
        self.components = axes.T
        transformed = normalized @ self.components
        self.weights = np.linalg.lstsq(
            np.column_stack([transformed, np.ones(len(transformed))]),
            target,
            rcond=None,
        )[0]
        mlflow.log_param("training_seed", 2026)
        mlflow.log_param("pipeline", "normalize-pca-regression")
        return None

    def live_predict(self, model_input, params=None, artifacts=None):
        frame = pd.DataFrame(model_input).copy()
        target = (
            frame.pop(TARGET_COLUMN).to_numpy(dtype=float)
            if TARGET_COLUMN in frame
            else None
        )
        corrupt = bool((params or {}).get("corrupt", False))

        with self.model_step("pipeline", kind="pipeline"):
            with self.model_step("input.normalize", kind="normalization") as step:
                features = frame.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
                step.observe_array("input", features)
                normalized = (features - self.mean) / self.scale
                step.observe_array("output", normalized)

            with self.model_step(
                "pca.transform", component="PCA", component_version="1"
            ) as step:
                transformed = normalized @ self.components
                if corrupt:
                    transformed = transformed.copy()
                    transformed[:, 0] += 12.0
                step.observe_array("output", transformed)

            with self.model_step(
                "regression.predict", component="linear-regression", component_version="1"
            ) as step:
                design = np.column_stack([transformed, np.ones(len(transformed))])
                prediction = design @ self.weights
                step.observe_array("output", prediction)

            if target is not None:
                with self.model_step("quality.evaluate", kind="evaluation") as step:
                    rmse = float(np.sqrt(np.mean((prediction - target) ** 2)))
                    # Keep the artifact compatible with the ModelStep API already
                    # installed in deployed gateways. Scalar values are represented
                    # as one-element arrays and therefore appear as ``*.mean``.
                    step.observe_array("rmse", [rmse])
                    step.observe_array("sample_count", [len(target)])

        return pd.DataFrame({"prediction": prediction})
