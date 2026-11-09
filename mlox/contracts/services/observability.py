"""Service capability contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Dict
from .capabilities import ServiceCapability


class AbstractObservabilityService(ABC):
    """Service capability for providers that accept application telemetry."""

    capabilities: ClassVar[set[ServiceCapability]] = {
        ServiceCapability.OBSERVABILITY
    }

    @abstractmethod
    def get_telemetry_env_binding(self) -> Dict[str, str]:
        """Return the environment required to export telemetry to this service."""
        pass


class AbstractMonitorService(ABC):
    """Service capability mixin for project-level monitoring providers."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.MONITOR}

    @abstractmethod
    def get_monitor_snapshot(self, bundle: Any) -> Dict[str, Any]:
        """Return a compact host/resource monitoring snapshot for one bundle."""
        pass


@dataclass(kw_only=True)
class AbstractTelemetryBindingService(ABC):
    """Opt-in capability for services accepting a telemetry binding."""

    capabilities: ClassVar[set[ServiceCapability]] = {
        ServiceCapability.TELEMETRY_BINDING
    }
    telemetry_uuid: str | None = None

    def get_bound_telemetry_env_binding(self) -> Dict[str, str] | None:
        """Return the environment exported by the configured telemetry provider."""

        telemetry_uuid = self.telemetry_uuid
        if telemetry_uuid is None:
            return None
        provider = self.get_dependent_service(  # type: ignore[attr-defined]
            telemetry_uuid,
            required_type=AbstractObservabilityService,
            required_capabilities={ServiceCapability.OBSERVABILITY},
        )
        if provider is None:
            raise ValueError(f"Telemetry service {telemetry_uuid!r} was not found.")
        environment = provider.get_telemetry_env_binding()  # type: ignore[attr-defined]
        if not isinstance(environment, dict):
            raise TypeError("Telemetry environment binding must be a dictionary.")
        result = {str(key): str(value) for key, value in environment.items()}
        result.setdefault(
            "OTEL_RESOURCE_ATTRIBUTES",
            "service.name="
            f"{getattr(self, 'name', '')},mlox.service.uuid={getattr(self, 'uuid', '')}",
        )
        return result

    def bind_telemetry(self, telemetry_uuid: str, conn) -> None:
        """Bind an observability provider and expose it to the deployment."""

        telemetry_uuid = str(telemetry_uuid).strip()
        if not telemetry_uuid:
            raise ValueError("Telemetry UUID must not be empty.")
        previous_uuid = self.telemetry_uuid
        self.telemetry_uuid = telemetry_uuid
        try:
            environment = self.get_bound_telemetry_env_binding()
            if self.state != "un-initialized":  # type: ignore[attr-defined]
                self._apply_telemetry_binding(
                    conn,
                    telemetry_uuid=telemetry_uuid,
                    environment=environment or {},
                )
        except Exception:
            self.telemetry_uuid = previous_uuid
            raise

    def unbind_telemetry(self, conn) -> None:
        """Remove this service's telemetry exporter configuration."""

        if self.telemetry_uuid is None:
            return
        if self.state != "un-initialized":  # type: ignore[attr-defined]
            self._remove_telemetry_binding(conn)
        self.telemetry_uuid = None

    @abstractmethod
    def _apply_telemetry_binding(
        self,
        conn,
        *,
        telemetry_uuid: str,
        environment: Dict[str, str],
    ) -> None:
        """Expose the selected telemetry provider to an initialized deployment."""

    @abstractmethod
    def _remove_telemetry_binding(self, conn) -> None:
        """Remove telemetry configuration from an initialized deployment."""
