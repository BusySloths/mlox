import os
import logging
import urllib3
from pathlib import Path

import numpy as np
import pandas as pd  # type: ignore

from datetime import datetime
from typing import List, Dict, Sequence
from abc import ABC, abstractmethod

import mlflow  # type: ignore
from mlflow.tracking import MlflowClient  # type: ignore


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


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
    def __init__(
        self,
        model: DeployableModel,
        model_class: str,
        code_paths: Sequence[str] | None = None,
    ) -> None:
        self.model = model
        self.model_class = model_class
        self.artifacts = None
        self.model_config = None
        self.tracking_uri = os.environ["MLFLOW_URI"]
        self.registry_uri = os.environ["MLFLOW_URI"]
        self.code_paths = list(code_paths) if code_paths is not None else ["./airml"]

    def track_model(
        self,
        params: Dict | None = None,
        input_example: np.ndarray | pd.DataFrame | None = None,
        inference_params: Dict | None = None,
    ):
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

            mlflow.pyfunc.log_model(
                artifact_path=self.model_class,
                python_model=self,
                code_path=self._resolve_code_paths_for_logging(),
                conda_env=self.get_conda_env(),
                signature=signature,
                input_example=input_example,
                registered_model_name=None,
                artifacts=artifacts,
            )

    def get_conda_env(
        self,
        name: str = "mlflow-models",
        python_version: str = "3.11.5",
        requirements_file: str = "requirements-mlops.txt",
    ) -> Dict:
        return {
            "name": name,
            "channels": ["defaults"],
            "dependencies": [
                f"python={python_version}",
                {"pip": [f"-r {requirements_file}"]},
            ],
        }

    def load_context(self, context):
        """This method is called when loading an MLflow model with pyfunc.load_model(),
            as soon as the Python Model is constructed.
        Args:
            context: MLflow context where the model artifact is stored.
        """
        logger.info(f"Load context called with context={context}")
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
        repo_root = Path(__file__).resolve().parents[1]
        for path_str in self.code_paths:
            path = Path(path_str)
            if not path.is_absolute():
                path = (repo_root / path).resolve()
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
            logger.warning(
                "No valid code paths found; defaulting to repository root %s.",
                repo_root,
            )
            resolved_paths.append(str(repo_root))
        return resolved_paths


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
