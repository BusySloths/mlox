"""Lazy access to the optional MLflow SDK for deployment adapters."""

from typing import Any


def create_mlflow_client(service_url: str, username: str, password: str) -> Any:
    """Configure and create a client only when a registry operation is requested."""

    import mlflow  # type: ignore

    from mlox.services.mlflow.artifacts import configure_mlflow_client

    configure_mlflow_client(service_url, username, password)
    return mlflow.tracking.MlflowClient()


def load_model_json_artifact(
    *,
    service_url: str,
    username: str,
    password: str,
    model_name: str,
    model_version: str,
    artifact_path: str,
) -> Any | None:
    """Load an artifact without requiring MLflow during adapter import."""

    from mlox.services.mlflow.artifacts import load_registered_model_json_artifact

    return load_registered_model_json_artifact(
        service_url=service_url,
        username=username,
        password=password,
        model_name=model_name,
        model_version=model_version,
        artifact_path=artifact_path,
    )
