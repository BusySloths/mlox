"""Service capability contracts."""

import logging
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Dict
from .capabilities import ServiceCapability
if TYPE_CHECKING:
    from mlox.infra import Infrastructure
    from mlox.secret_manager import AbstractSecretManager
logger = logging.getLogger(__name__)


class AbstractSecretManagerService(ABC):
    """Service capability mixin for services that provide a secret manager client."""

    capabilities: ClassVar[set[ServiceCapability]] = {ServiceCapability.SECRET_MANAGER}

    @abstractmethod
    def get_secret_manager(self, infra: "Infrastructure") -> "AbstractSecretManager":
        """Return an AbstractSecretManager client for this service."""
        pass

    def get_secret_manager_env_binding(
        self, binding_id: str | None = None
    ) -> Dict[str, str]:
        """Return shared or binding-specific environment configuration."""

        manager = self.get_secret_manager(getattr(self, "_service_lookup", None))
        return self._build_secret_manager_env_binding(manager)

    def revoke_secret_manager_env_binding(
        self, binding_id: str | None = None
    ) -> None:
        """Revoke exported access when supported by the provider."""

    def get_secret_manager_binding_label(self, binding_id: str) -> str | None:
        """Return a provider-specific credential label when one is available."""

        return None

    @staticmethod
    def _build_secret_manager_env_binding(
        manager: "AbstractSecretManager",
    ) -> Dict[str, str]:
        """Encode a secret-manager client as the standard MLOX environment."""

        from mlox.secret_manager import (
            SECRET_MANAGER_KEYFILE_ENV,
            SECRET_MANAGER_KEYFILE_PW_ENV,
            get_encrypted_access_keyfile,
        )

        password = secrets.token_urlsafe(32)
        return {
            SECRET_MANAGER_KEYFILE_ENV: get_encrypted_access_keyfile(
                manager, password
            ),
            SECRET_MANAGER_KEYFILE_PW_ENV: password,
        }


@dataclass(kw_only=True)
class AbstractSecretManagerBindingService(ABC):
    """Opt-in capability for services accepting a secret-manager binding."""

    capabilities: ClassVar[set[ServiceCapability]] = {
        ServiceCapability.SECRET_MANAGER_BINDING
    }
    secret_manager_uuid: str | None = None

    def _get_secret_manager_provider(
        self, manager_uuid: str
    ) -> AbstractSecretManagerService:
        provider = self.get_dependent_service(  # type: ignore[attr-defined]
            manager_uuid,
            required_type=AbstractSecretManagerService,
            required_capabilities={ServiceCapability.SECRET_MANAGER},
        )
        if provider is None:
            raise ValueError(f"Secret-manager service {manager_uuid!r} was not found.")
        return provider

    def get_bound_secret_manager_env_binding(self) -> Dict[str, str] | None:
        """Return the environment exported by the configured provider."""

        manager_uuid = self.secret_manager_uuid
        if manager_uuid is None:
            return None
        provider = self._get_secret_manager_provider(manager_uuid)
        binding_id = str(getattr(self, "uuid", "") or "")
        environment = provider.get_secret_manager_env_binding(binding_id)
        if not isinstance(environment, dict):
            raise TypeError("Secret-manager environment binding must be a dictionary.")
        return {str(key): str(value) for key, value in environment.items()}

    def bind_secret_manager(self, manager_uuid: str, conn) -> None:
        """Bind a secret-manager provider and expose it to the deployment."""

        manager_uuid = str(manager_uuid).strip()
        if not manager_uuid:
            raise ValueError("Secret-manager UUID must not be empty.")
        previous_uuid = self.secret_manager_uuid
        if manager_uuid == previous_uuid:
            return
        self.secret_manager_uuid = manager_uuid
        try:
            if self.state != "un-initialized":  # type: ignore[attr-defined]
                environment = self.get_bound_secret_manager_env_binding()
                self._apply_secret_manager_binding(
                    conn,
                    manager_uuid=manager_uuid,
                    environment=environment or {},
                )
        except Exception:
            try:
                provider = self._get_secret_manager_provider(manager_uuid)
                provider.revoke_secret_manager_env_binding(
                    str(getattr(self, "uuid", "") or "")
                )
            except Exception:
                logger.warning(
                    "Could not roll back secret-manager credential for %s.",
                    manager_uuid,
                    exc_info=True,
                )
            self.secret_manager_uuid = previous_uuid
            raise
        if previous_uuid and previous_uuid != manager_uuid:
            try:
                previous_provider = self._get_secret_manager_provider(previous_uuid)
                previous_provider.revoke_secret_manager_env_binding(
                    str(getattr(self, "uuid", "") or "")
                )
            except Exception:
                logger.warning(
                    "Could not revoke the previous secret-manager credential for %s.",
                    previous_uuid,
                    exc_info=True,
                )

    def unbind_secret_manager(self, conn) -> None:
        """Remove this service's secret-manager access configuration."""

        if self.secret_manager_uuid is None:
            return
        provider = self._get_secret_manager_provider(self.secret_manager_uuid)
        if self.state != "un-initialized":  # type: ignore[attr-defined]
            self._remove_secret_manager_binding(conn)
        provider.revoke_secret_manager_env_binding(
            str(getattr(self, "uuid", "") or "")
        )
        self.secret_manager_uuid = None

    @abstractmethod
    def _apply_secret_manager_binding(
        self,
        conn,
        *,
        manager_uuid: str,
        environment: Dict[str, str],
    ) -> None:
        """Expose the selected provider to an initialized deployment."""

    @abstractmethod
    def _remove_secret_manager_binding(self, conn) -> None:
        """Remove secret-manager access from an initialized deployment."""
