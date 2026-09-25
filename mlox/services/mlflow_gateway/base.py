"""Backend-neutral behavior for MLflow Gateway services."""

import json
import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, cast

from mlox.service import (
    AbstractHealthService,
    AbstractModelRegistryService,
    AbstractModelServerService,
    AbstractService,
    ServiceCapability,
    service_health_payload,
)

logger = logging.getLogger(__name__)


def _resolved_text(value: str) -> str:
    if value.strip().startswith("${") and value.strip().endswith("}"):
        return ""
    return value


def _resolved_setting(value: str | int | float, default: str) -> str:
    resolved = _resolved_text(str(value))
    return resolved or default


@dataclass
class MLFlowGatewayService(
    AbstractService, AbstractHealthService, AbstractModelServerService
):
    """Common MLflow Gateway configuration and model-server operations."""

    capabilities = {ServiceCapability.MODEL_SERVER, ServiceCapability.HEALTH}

    dockerfile: str
    serve_script: str
    start_script: str
    port: str | int
    tracking_uri: str
    tracking_user: str
    tracking_pw: str
    requirements_txt: str = ""
    cache_max_models: str | int = "10"
    cache_ttl_days: str | int | float = "10"
    user: str = "admin"
    pw: str = "s3cr3t"
    service_url: str = field(init=False, default="")

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.target_path.endswith(f"-{self.port}"):
            self.target_path = f"{self.target_path}-{self.port}"

    def get_health(self, conn) -> Dict[str, Any]:
        return service_health_payload(self, self.check(conn))

    def get_secrets(self) -> Dict[str, Dict]:
        secrets: Dict[str, Dict] = {}
        secrets["mlflow_gateway_basic_auth"] = {
            "username": self.user,
            "password": self.pw,
            "service_url": self.service_url,
        }
        secrets["mlflow_tracking_credentials"] = {
            "username": self.tracking_user,
            "password": self.tracking_pw,
            "tracking_uri": self.tracking_uri,
            "cache_max_models": str(self.cache_max_models),
            "cache_ttl_days": str(self.cache_ttl_days),
        }
        return secrets

    def get_registry(self) -> AbstractModelRegistryService | None:
        if not self.registry_uuid:
            logger.warning("No registry UUID set for MLflow Gateway service.")
            return None
        registry = self.get_dependent_service(self.registry_uuid)
        if not registry:
            logger.warning("No registry service found for UUID %s", self.registry_uuid)
            return None
        return cast(AbstractModelRegistryService, registry)  # type: ignore

    def is_model(self, name: str) -> bool:
        if ":" not in name:
            return False
        parts = name.split(":")
        if len(parts) != 3:
            return False
        registry_name, model_name, version = parts
        registry_service = self.get_dependent_service_by_name(registry_name)
        if not registry_service:
            return False
        return bool(model_name and version)

    def list_supported_models(self) -> List[Dict[str, Any]]:
        registry = self.get_registry()
        if not registry:
            return []
        return [
            {
                "name": str(model.get("Model", "-")),
                "version": str(model.get("Version", "-")),
                "type": "MLflow Gateway",
                "status": str(model.get("Status", self.state)),
                "model_uri": f"{model.get('Model', '-')}/{model.get('Version', '-')}",
            }
            for model in registry.list_models()
        ]

    def get_example(
        self,
        model: Dict[str, Any] | None = None,
        input_example: Any | None = None,
    ) -> str:
        model_name = str((model or {}).get("name") or "ModelName")
        model_version = str((model or {}).get("version") or "1")
        payload_input = _prediction_payload_input(input_example)
        payload = {
            "params": {},
            "registry_model_name": model_name,
            "registry_model_version": model_version,
            **payload_input,
        }
        return "\n".join(
            [
                f"curl -k -u '{self.user}:{self.pw}' \\",
                f"  {self.service_url.rstrip('/')}/prod/predict \\",
                "  -H 'Content-Type: application/json' \\",
                f"  -d '{json.dumps(payload)}'",
            ]
        )


def _prediction_payload_input(input_example: Any | None) -> Dict[str, Any]:
    if (
        isinstance(input_example, dict)
        and isinstance(input_example.get("columns"), list)
        and isinstance(input_example.get("data"), list)
    ):
        payload = {
            "columns": input_example["columns"],
            "data": input_example["data"],
        }
        if "index" in input_example:
            payload["index"] = input_example["index"]
        return {"dataframe_split": payload}
    if isinstance(input_example, dict) and isinstance(input_example.get("data"), list):
        return {"input_data": input_example["data"]}
    if input_example is not None:
        return {"input_data": input_example}
    return {"input_data": [[0.0, 1.0, 2.0]]}
