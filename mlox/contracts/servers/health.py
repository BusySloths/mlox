"""Server capability contracts."""

from abc import ABC
from typing import Any, ClassVar, Dict
from mlox.logs import LogSource
from .capabilities import ServerCapability

SERVER_HEALTHY_STATES = {"running"}
SENSITIVE_HEALTH_KEY_PARTS = ("token", "password", "secret")


def _redact_health_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SENSITIVE_HEALTH_KEY_PARTS):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_health_values(item)
        return redacted
    if isinstance(value, list):
        return [_redact_health_values(item) for item in value]
    return value


class AbstractLogServer(LogSource):
    """Optional server capability for named log sources."""

    capabilities: ClassVar[set[ServerCapability]] = {ServerCapability.LOGS}


class AbstractHealthServer(ABC):
    """Optional server capability for richer live health information."""

    capabilities: ClassVar[set[ServerCapability]] = {ServerCapability.HEALTH}

    def get_health(self, no_cache: bool = True) -> Dict[str, Any]:
        state = str(getattr(self, "state", "unknown") or "unknown")
        health: Dict[str, Any] = {
            "state": state,
            "status": state,
            "healthy": state in SERVER_HEALTHY_STATES,
        }

        try:
            health["connection.is_reachable"] = bool(self.test_connection())
        except Exception as exc:
            health["connection.is_reachable"] = False
            health["connection.error"] = str(exc)

        try:
            health["server_info"] = _redact_health_values(
                self.get_server_info(no_cache=no_cache)
            )
        except Exception as exc:
            health["server_info.error"] = str(exc)

        try:
            backend_status = _redact_health_values(self.get_backend_status())
            if isinstance(backend_status, dict):
                health.update(backend_status)
                if backend_status.get("backend.is_running") is False:
                    health["healthy"] = False
        except Exception as exc:
            health["backend.error"] = str(exc)
            health["healthy"] = False

        if health.get("connection.is_reachable") is False:
            health["healthy"] = False
        return health
