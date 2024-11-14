import os

import numpy as np
import pandas as pd
import logging

from datetime import datetime
from typing import List, Dict
from abc import ABC, abstractmethod

import mlflow  # type: ignore
from mlflow.tracking import MlflowClient  # type: ignore


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MLOpsModelInterface(ABC):
    @abstractmethod
    def live_predict(
        self,
        model_input: np.ndarray,
        params: Dict | None = None,
        artifacts: Dict | None = None,
    ) -> pd.DataFrame:
        pass

    @abstractmethod
    def tracking(self, mlflow, params: Dict | None = None) -> Dict | None:
        pass


class MlopsModelWrapper(mlflow.pyfunc.PythonModel):
    def __init__(self, model: MLOpsModelInterface, model_class: str) -> None:
        self.model = model
        self.model_class = model_class
        self.artifacts = None
        self.model_config = None

    def track_model(
        self,
        params: Dict | None = None,
        input_example: np.ndarray | None = None,
        inference_params: Dict | None = None,
    ):
        # os.environ["DATABRICKS_HOST"] = read_secret_as_yaml("DATABRICKS").get(
        #     "DATABRICKS_URL", None
        # )
        # os.environ["DATABRICKS_TOKEN"] = read_secret_as_yaml("DATABRICKS").get(
        #     "DATABRICKS_TOKEN", None
        # )
        # mlflow.set_tracking_uri("databricks")
        # mlflow.set_registry_uri("databricks")
        # mlflow.set_experiment(f"/Shared/{self.model_class}")

        # ASSERT environ vars:
        # - MLFLOW_TRACKING_USERNAME, MLFLOW_TRACKING_PASSWORD, MLFLOW_URI
        os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
        mlflow.set_tracking_uri(os.environ["MLFLOW_URI"])
        mlflow.set_registry_uri(os.environ["MLFLOW_URI"])
        mlflow.set_experiment(f"{self.model_class}")

        run_tags = {"model": self.model_class}
        with mlflow.start_run(log_system_metrics=True, tags=run_tags) as run:
            artifacts = self.model.tracking(mlflow, params=params)

            signature = None
            if input_example is not None:
                signature = mlflow.models.infer_signature(
                    input_example,
                    self.model.live_predict(
                        input_example, params=params, artifacts=artifacts
                    ),
                    params=inference_params,
                )

            if artifacts is None:
                artifacts = dict()
            artifacts["keyfile.json"] = "./keyfile.json"

            mlflow.set_tag("python_class", str(self.model.__class__))

            mlflow.pyfunc.log_model(
                artifact_path=self.model_class,
                python_model=self,
                code_path=["./mlox/"],
                conda_env=self.get_conda_env(),
                signature=signature,
                input_example=input_example,
                registered_model_name=None,
                artifacts=artifacts,
            )

    def get_conda_env(self) -> Dict:
        return {
            "name": "mlflow-models",
            "channels": ["defaults"],
            "dependencies": [
                "python=3.11.5",
                {"pip": ["-r requirements-mlops-1.txt"]},
            ],
        }

    def load_context(self, context):
        """This method is called when loading an MLflow model with pyfunc.load_model(),
            as soon as the Python Model is constructed.
        Args:
            context: MLflow context where the model artifact is stored.
        """
        logger.info(f"Load context called with context={context}")
        self.artifacts = context.artifacts
        logger.info(f"Load artifacts {list(self.artifacts.keys())}")

        self.model_config = context.model_config
        if self.model_config is not None:
            logger.info(f"Load model_config {list(self.model_config.keys())}")

        logger.info("Get keyfile as string and store to env var")
        keyfile_path = self.artifacts["keyfile.json"]
        with open(keyfile_path, "r") as file:
            keyfile_content = file.read()
            os.environ["GOOGLE_SECRET_ACCESSOR_CREDENTIALS_DICT"] = keyfile_content
        logger.info("Done.")

    def predict(self, context, model_input, params=None) -> pd.DataFrame:
        logger.info("Incoming request with time stamp: ", datetime.now().isoformat())
        logger.info("Model config: ", self.model_config)
        logger.info("Artifacts: ", self.artifacts)
        logger.info("Params: ", params)
        logger.info("Input: ", model_input)

        try:
            res = self.model.live_predict(
                model_input, params=params, artifacts=self.artifacts
            )
        except Exception as e:
            # Log the exception and re-raise it.
            logger.exception(f"Error in prediction")
            raise e
        logger.info(f"Prediction result:\n{res}", extra=res.to_dict())  # type: ignore
        return res


def list_versions_for_model(model_name: str) -> List:
    # os.environ["DATABRICKS_HOST"] = read_secret_as_yaml("DATABRICKS").get(
    #     "DATABRICKS_URL", None
    # )
    # os.environ["DATABRICKS_TOKEN"] = read_secret_as_yaml("DATABRICKS").get(
    #     "DATABRICKS_TOKEN", None
    # )
    # mlflow.set_tracking_uri("databricks")
    # mlflow.set_registry_uri("databricks")
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    mlflow.set_tracking_uri(os.environ["MLFLOW_URI"])
    mlflow.set_registry_uri(os.environ["MLFLOW_URI"])

    names = list()
    client = MlflowClient()
    filter_string = f"name='{model_name}'"
    for rm in client.search_model_versions(filter_string):
        # logger.info("-  ", rm)
        names.append(rm)
    return names


if __name__ == "__main__":
    print(list_versions_for_model(model_name="Test"))
