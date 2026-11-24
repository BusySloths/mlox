"""Service contract for direct and composite local tunnel connections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from mlox.tunnel import TunnelBinding, TunnelPlan

if TYPE_CHECKING:
    from mlox.infra import Infrastructure


class AbstractTunnelService(ABC):
    @abstractmethod
    def tunnel_plan(self, infra: Infrastructure) -> TunnelPlan:
        """Describe required endpoints without opening connections."""
        raise NotImplementedError

    @abstractmethod
    def tunnel_secrets(self, infra: Infrastructure, bindings: tuple[TunnelBinding, ...]) -> dict[str, Any]:
        """Produce ephemeral local connection details without changing stored secrets."""
        raise NotImplementedError

    def tunnel_health(self, infra: Infrastructure, bindings: tuple[TunnelBinding, ...]) -> dict[str, Any] | None:
        """Optionally run an application health check through local bindings."""
        return None
