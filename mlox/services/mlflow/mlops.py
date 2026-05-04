import os
import logging
import shutil
import tempfile
from pathlib import Path
from contextlib import contextmanager

import numpy as np
import pandas as pd  # type: ignore

from datetime import datetime
from typing import List, Dict, Sequence, Iterator
from abc import ABC, abstractmethod

import mlflow  # type: ignore
from mlflow.models.model import ModelInfo  # type: ignore
from mlflow.tracking import MlflowClient  # type: ignore

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


logger = logging.getLogger(__name__)

_EXCLUDED_CODE_PATH_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "venv",
    }
)


class DeployableModel(ABC):
    @abstractmethod
    def live_predict(
        self,
        input: np.ndarray | pd.DataFrame,
        params: Dict | None = None,
        artifacts: Dict | None = None,
    ) -> pd.DataFrame:
        pass

    @abstractmethod
    def tracked_training(self, params: Dict | None = None) -> Dict | None:
        pass


class MLFlowDeployableModelService(mlflow.pyfunc.PythonModel):  # type: ignore
    registered_model_name: str | None
    registered_model_version: int | None
    requirements_file: str | None
    requirements_python_version: str | None
    run_id: str | None
    logged_model_info: ModelInfo | None

    def __init__(
        self,
        model: DeployableModel,
        model_class: str,
        code_paths: Sequence[str] | None = None,
        requirements_file: str | None = None,
        requirements_python_version: str = "3.12.5",
    ) -> None:
        self.model = model
        self.model_class = model_class
        self.artifacts = None
        self.model_config = None
        self.tracking_uri = os.environ["MLFLOW_URI"]
        self.registry_uri = os.environ["MLFLOW_URI"]
        self.code_paths = list(code_paths) if code_paths is not None else []
        self.registered_model_name = None
        self.registered_model_version = None
        self.requirements_file = requirements_file
        self.requirements_python_version = requirements_python_version
        self.run_id = None
        self.logged_model_info = None

    def set_registered_model_name(self, registered_model_name: str | None) -> None:
        if registered_model_name:
            logger.info("Setting registered model name to '%s'", registered_model_name)
        else:
            logger.info(
                "Clearing registered model name means that model won't be registered."
            )
        self.registered_model_name = registered_model_name

    def track_model(
        self,
        params: Dict | None = None,
        input_example: np.ndarray | pd.DataFrame | None = None,
        inference_params: Dict | None = None,
    ) -> ModelInfo:
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_registry_uri(self.registry_uri)
        mlflow.set_experiment(f"{self.model_class}")

        run_tags = {"model": self.model_class}
        with mlflow.start_run(log_system_metrics=True, tags=run_tags):
            with mlflow.start_span("tracked-training") as span:
                span.set_inputs({"params": params})
                artifacts = self.model.tracked_training(params=params)
                span.set_attribute("attrib1", "value1")
                span.set_outputs({"artifacts": artifacts})

            signature: mlflow.models.ModelSignature | None = None
            if input_example is not None:
                with mlflow.start_span("infer-signature") as span:
                    logger.info(
                        "Inferring signature for the model input with type %s",
                        type(input_example),
                    )
                    signature = mlflow.models.infer_signature(
                        input_example,
                        self.model.live_predict(
                            input_example, params=params, artifacts=artifacts
                        ),
                        params=inference_params,
                    )
                    logger.info("Signature inferred successfully: %s", signature)
            else:
                logger.info("No input example provided; skipping signature inference.")

            if artifacts is None:
                artifacts = dict()

            mlflow.set_tag("python_class", str(self.model.__class__))

            with self._prepared_code_paths_for_logging() as prepared_code_paths:
                model_info = mlflow.pyfunc.log_model(
                    name=self.model_class,
                    python_model=self,
                    code_paths=prepared_code_paths or None,
                    conda_env=self.get_conda_env(),
                    signature=signature,
                    input_example=input_example,
                    registered_model_name=self.registered_model_name,
                    artifacts=artifacts,
                )
            self._store_logged_model_info(model_info)
            return model_info

    def get_conda_env(self) -> Dict:
        """Create a conda environment for the MLflow model."""
        if self.requirements_file is None:
            return {
                "name": "mlflow-models",
                "channels": ["defaults"],
                "dependencies": [
                    f"python={self.requirements_python_version or '3.12.5'}",
                    {"pip": [f"mlflow=={mlflow.__version__}"]},
                ],
            }
        return {
            "name": "mlflow-models",
            "channels": ["defaults"],
            "dependencies": [
                f"python={self.requirements_python_version or '3.12.5'}",
                {"pip": [f"-r {self.requirements_file}"]},
            ],
        }

    def load_context(self, context):
        """This method is called when loading an MLflow model with pyfunc.load_model(),
            as soon as the Python Model is constructed.
        Args:
            context: MLflow context where the model artifact is stored.
        """
        logger.info(f"Load context called with context={context}")
        # self._add_code_paths_to_pythonpath(context)
        self.artifacts = context.artifacts or {}
        logger.info(f"Load artifacts {list(self.artifacts.keys())}")
        self.model_config = context.model_config
        if self.model_config is not None:
            logger.info(f"Load model_config {list(self.model_config.keys())}")

        logger.info("Done.")

    def predict(self, context, model_input, params=None) -> pd.DataFrame:
        logger.info(f"Incoming request with time stamp: {datetime.now().isoformat()}")
        logger.info(f"Model config: {self.model_config}")
        logger.info(f"Artifacts: {self.artifacts}")
        logger.info(f"Params: {params}")
        logger.info(f"Input: {model_input}")
        logger.info(f"Input type: {type(model_input)}")

        if params is None:
            logger.info("No params provided; using empty dict.")
            params = {}

        logger.info("Entering prediction.")
        try:
            logger.info("Calling live_predict method of the model.")
            logger.info(f"Model: {self.model}")
            res = self.model.live_predict(
                model_input, params=params, artifacts=self.artifacts
            )
        except Exception as e:
            # Log the exception and re-raise it.
            logger.error(f"Error in prediction: {e}", exc_info=True)
            res = pd.DataFrame({"error": [str(e)]})

        logger.info(f"Prediction result:\n{res}")  # type: ignore
        return res

    def _resolve_code_paths_for_logging(self) -> List[str]:
        resolved_paths: List[str] = []
        base_dir = Path.cwd()
        for path_str in self.code_paths:
            path = Path(path_str).expanduser()
            if not path.is_absolute():
                path = (base_dir / path).resolve()
            if path.exists():
                resolved_paths.append(str(path))
            else:
                logger.warning(
                    "Configured code path '%s' does not exist (resolved to %s); "
                    "it will be skipped during logging.",
                    path_str,
                    path,
                )
        if not resolved_paths:
            logger.info("No valid code paths configured for MLflow model logging.")
        return resolved_paths

    def _ignore_code_path_entries(
        self,
        _directory: str,
        names: list[str],
    ) -> set[str]:
        return {name for name in names if name in _EXCLUDED_CODE_PATH_NAMES}

    @contextmanager
    def _prepared_code_paths_for_logging(self) -> Iterator[List[str]]:
        prepared_paths: List[str] = []
        temp_dirs: list[tempfile.TemporaryDirectory[str]] = []
        try:
            for path_str in self._resolve_code_paths_for_logging():
                path = Path(path_str)
                if path.is_dir():
                    temp_dir = tempfile.TemporaryDirectory(
                        prefix="mlox-mlflow-code-path-"
                    )
                    temp_dirs.append(temp_dir)
                    staged_path = Path(temp_dir.name) / path.name
                    shutil.copytree(
                        path,
                        staged_path,
                        ignore=self._ignore_code_path_entries,
                    )
                    prepared_paths.append(str(staged_path))
                else:
                    prepared_paths.append(str(path))
            yield prepared_paths
        finally:
            for temp_dir in reversed(temp_dirs):
                temp_dir.cleanup()

    def _store_logged_model_info(self, model_info: ModelInfo) -> None:
        self.logged_model_info = model_info
        self.run_id = model_info.run_id
        self.registered_model_version = model_info.registered_model_version
        logger.info(
            "Logged MLflow model '%s' with run_id=%s, model_uri=%s, "
            "registered_model_version=%s",
            self.model_class,
            self.run_id,
            model_info.model_uri,
            self.registered_model_version,
        )


def list_versions_for_model(model_name: str) -> List:
    mlflow.set_tracking_uri(os.environ["MLFLOW_URI"])
    mlflow.set_registry_uri(os.environ["MLFLOW_URI"])

    names = list()
    client = MlflowClient()
    filter_string = f"name='{model_name}'"
    for rm in client.search_model_versions(filter_string):
        names.append(rm)
    return names


if __name__ == "__main__":
    logger.info(list_versions_for_model(model_name="Test"))
