"""Service capability contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List
from .capabilities import ServiceCapability


@dataclass
class AbstractWorkflowOrchestratorService(ABC):
    """Service capability mixin for workflow orchestration providers."""

    capabilities: ClassVar[set[ServiceCapability]] = {
        ServiceCapability.WORKFLOW_ORCHESTRATOR
    }

    @abstractmethod
    def list_workflows(self) -> List[Dict[str, Any]]:
        """Return workflow/DAG metadata including recent run information."""
        pass
