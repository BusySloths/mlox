import logging
import numpy as np
import pandas as pd

from typing import Dict
from datetime import datetime

from mlox.services.mlflow.models import MlopsModelWrapper, MLOpsModelInterface

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MyTrackedModel(MLOpsModelInterface):
    # The whole object and everything inside will be logged/persisted.

    my_model_weights: pd.DataFrame | None = None

    def live_predict(
        self,
        model_input: np.ndarray,
        params: Dict | None = None,
        artifacts: Dict | None = None,
    ) -> pd.DataFrame:
        if model_input.ndim < 2:
            model_input = model_input.reshape(1, -1)

        logger.info(f"New call {datetime.now().isoformat()} : with params {params}")
        logger.info(f"Received model_input data = {model_input[0, 0]}")
        df_res = pd.DataFrame()
        if self.my_model_weights is not None:
            df_res = self.my_model_weights.copy()
        logger.info("Stored model weights are =", df_res)
        df_res["ColA"] = model_input[0, 0]

        logger.info("Check params.")
        if params is not None:
            my_param = params.get("my_param", False)
            print(f"Values = {my_param}")
        logger.info("Done. Return results")
        return df_res

    def tracking(self, mlflow, params: Dict | None = None) -> Dict | None:
        if params is not None:
            print(f"Tracking: my_train_param_1={params.get('my_train_param_1', None)}")

        # DO TRAINING AND STUFF
        df_train = pd.DataFrame([[0, 1], [2, 3]], columns=["ColA", "ColB"])
        self.my_model_weights = df_train.copy()

        my_train_metrics = {"ACC": 0.8, "AUC": 0.79}

        mlflow.log_metrics(my_train_metrics)

        dataset = mlflow.data.from_pandas(df_train)
        mlflow.log_input(dataset=dataset, context="training")

        mlflow.set_tag("dataset", "artificial")
        mlflow.set_tag("dataset", "artificial")
        mlflow.log_params({"a_logged_param": "a_logged_param_value"})

        # log additional files that you might need during inference
        artifacts = {"my_readme.md": "./README.md"}
        return artifacts


def tracked_experiment():
    my_model = MyTrackedModel()

    mlops = MlopsModelWrapper(my_model, "krabbelbox")

    # mlops.track_model sets up mlops and calls my_model.tracking
    mlops.track_model(
        params={"my_train_param_1": "my_train_param_1_value"},  # these parameters are
        input_example=np.array(
            [["my_input_example_value"]]
        ),  # as of now inputs must be wrapped in np.numpy
        inference_params={
            "my_param": False,
            "my_additional_inference_param_1": False,
        },  # this is optional (=additional parameters during inference)
    )


def local_experiment():
    my_model = MyTrackedModel()
    my_model.my_model_weights = pd.DataFrame(
        [[0, 1], [2, 3]], columns=["ColocalA", "ColocalB"]
    )
    mlops = MlopsModelWrapper(my_model, "krabbelbox")

    # mlops.track_model sets up mlops and calls my_model.tracking
    print(
        mlops.predict(
            None,
            model_input=np.array(
                [["my_input_example_value"]]
            ),  # as of now inputs must be wrapped in np.numpy
            params={
                "my_param": True,
                "my_additional_inference_param_1": False,
            },  # this is optional (=additional parameters during inference)
        )
    )


if __name__ == "__main__":
    tracked_experiment()
    # local_experiment()
