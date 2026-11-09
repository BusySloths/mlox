"""Service capability contracts."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List
from .capabilities import ServiceCapability


@dataclass
class AbstractModelRegistryService(ABC):
    """Service capability mixin for model registry services."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.MODEL_REGISTRY}

    @abstractmethod
    def list_models(self, filter: str | None = None) -> List[Dict[str, Any]]:
        pass

    def load_artifact(
        self,
        model_name: str,
        model_version: str,
        artifact_path: str,
    ) -> Any | None:
        """Load a model artifact when supported by the registry implementation."""

        return None


@dataclass
class AbstractModelServerService(ABC):
    """Service capability mixin for model-serving services."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.MODEL_SERVER}
    registry_uuid: str | None = field(default=None, kw_only=True)

    @abstractmethod
    def is_model(self, name: str) -> bool:
        pass

    @abstractmethod
    def get_registry(self) -> AbstractModelRegistryService | None:
        pass

    def list_supported_models(self) -> List[Dict[str, Any]]:
        """Return models this endpoint can serve or route to."""

        return []

    def get_example(
        self,
        model: Dict[str, Any] | None = None,
        input_example: Any | None = None,
    ) -> str:
        """Return a concrete invocation example for this model endpoint."""

        url = str(getattr(self, "service_url", "")).rstrip("/")
        if not url:
            return "No endpoint URL is available yet."
        body = input_example if input_example is not None else {}
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        return (
            "curl -k "
            f"{url} "
            "-H 'Content-Type: application/json' "
            f"-d '{json.dumps(body)}'"
        )
