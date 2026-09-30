"""Register the Operations demonstrator model and assign its champion alias."""

from pathlib import Path
import logging

from examples.operations_demo.model import (
    MODEL_NAME,
    OperationsDemoModel,
    demonstration_batch,
)
from examples.runtime import setup_runtime
from mlox.services.mlflow.mlops import MLFlowDeployableModelService


def register_model() -> None:
    client, _ = setup_runtime(tracking=True)
    try:
        root = Path(__file__).resolve().parents[2]
        service = MLFlowDeployableModelService(
            OperationsDemoModel(),
            MODEL_NAME,
            code_paths=[str(root / "mlox"), str(root / "examples")],
        )
        service.set_registered_model_name(MODEL_NAME)
        info = service.track_model(
            input_example=demonstration_batch(8),
            inference_params={"corrupt": False},
        )
        service.set_alias("champion")
        print(f"Registered {MODEL_NAME}@champion from {info.model_uri}")
    finally:
        if client:
            client.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register_model()
