"""Service capability contracts."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict
from mlox.logs import LogSource
from .capabilities import ServiceCapability


class AbstractLogService(LogSource):
    """Optional service capability for named log sources."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.LOGS}


class AbstractHealthService(ABC):
    """Optional service capability for richer live health information."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.HEALTH}

    @abstractmethod
    def get_health(self, conn) -> Dict[str, Any]:
        """Return a rich live health payload for this service."""
        pass


class AbstractProxyService(ABC):
    """A service that manages routes to relayed services or endpoints."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.PROXY}

    @abstractmethod
    def add_route(self, conn, *, hostname: str, backend: str, service_uuid: str = "", **options: Any) -> None:
        """Create a route, optionally linked to a managed service UUID."""

    @abstractmethod
    def remove_route(self, conn, *, hostname: str) -> None:
        """Remove the route for a hostname."""

    @abstractmethod
    def list_routes(self) -> Dict[str, Dict[str, Any]]:
        """Return configured routes and their optional service references."""

    def list_relayed_services(self) -> set[str]:
        """Return explicitly linked service UUIDs; legacy routes may be unlinked."""
        return {str(route['service_uuid']) for route in self.list_routes().values() if route.get('service_uuid')}


class AbstractWebUIService(ABC):
    """Service capability mixin for services with a browser-facing UI."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.WEB_UI}
    web_ui_url_label: ClassVar[str | None] = None
    web_ui_login_fields: ClassVar[tuple[str, ...]] = ()

    def get_web_ui_address(self) -> str:
        """Return the preferred browser URL for this service, if available."""

        urls = getattr(self, "service_urls", {}) or {}
        if self.web_ui_url_label:
            url = urls.get(self.web_ui_url_label)
            if url:
                return str(url)

        for label, url in urls.items():
            label_text = str(label).lower()
            if any(
                term in label_text for term in ("ui", "dashboard", "console", "login")
            ):
                return str(url)

        url = getattr(self, "service_url", "")
        return str(url or "")

    def get_web_ui_login(self, bundle: Any | None = None) -> dict[str, str]:
        """Return browser-login credentials for this service, if available."""

        credentials: dict[str, str] = {}
        username = getattr(self, "ui_user", None) or getattr(self, "root_user", None)
        password = getattr(self, "ui_pw", None) or getattr(self, "root_password", None)
        if username:
            credentials["username"] = str(username)
        if password:
            credentials["password"] = str(password)
        return credentials
