"""Register the Operations demonstrator model and assign its champion alias."""

from pathlib import Path
import logging

from mlflow.models import ModelSignature
from mlflow.types.schema import ColSpec, Schema

from examples.operations_demo.model import (
    FEATURE_COLUMNS,
    MODEL_NAME,
    OperationsDemoModel,
    TARGET_COLUMN,
    demonstration_batch,
)
from examples.runtime import setup_runtime
from mlox.services.mlflow.mlops import MLFlowDeployableModelService


def _serving_signature() -> ModelSignature:
    """Allow immediate-label and prediction-only calls to the same model."""

    return ModelSignature(
        inputs=Schema(
            [ColSpec("double", name) for name in FEATURE_COLUMNS]
            + [ColSpec("double", TARGET_COLUMN, required=False)]
        ),
        outputs=Schema([ColSpec("double", "prediction")]),
    )


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
            signature=_serving_signature(),
        )
        service.set_alias("champion")
        print(f"Registered {MODEL_NAME}@champion from {info.model_uri}")
    finally:
        if client:
            client.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    register_model()
