"""Public runtime API for one encrypted MLOX project workspace."""

from __future__ import annotations

import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Optional

from mlox.application.result import OperationResult
from mlox.application.use_cases import models, project, servers, services
from mlox.config import (
    get_stacks_path,
    load_all_server_configs,
    load_all_service_configs,
    load_config,
    load_service_config_by_id,
)
from mlox.infra import Infrastructure
from mlox.project.repository import SqlCipherRepository
from mlox.project.secrets import (
    EmbeddedSecretManager,
    SecretManagerDescriptor,
    UnavailableSecretManager,
)
from mlox.project.state import WorkspaceState
from mlox.secret_manager import AbstractSecretManager
from mlox.service import AbstractSecretManagerService
from mlox.utils import save_to_json

DEFAULT_MLSERVER_TEMPLATE_ID = "mlflow-mlserver-3.8.1-docker"


class ProjectWorkspace:
    """Loaded project state, persistence boundary, and application API."""

    def __init__(
        self,
        repository: SqlCipherRepository,
        state: WorkspaceState,
    ) -> None:
        self._repository = repository
        self._state = state
        self._embedded_secrets = EmbeddedSecretManager(repository)
        self._secrets = self._resolve_secret_manager()

    @property
    def name(self) -> str:
        return self._state.name

    @name.setter
    def name(self, value: str) -> None:
        self._state.name = value

    @property
    def descr(self) -> str:
        return self._state.descr

    @descr.setter
    def descr(self, value: str) -> None:
        self._state.descr = value

    @property
    def version(self) -> str:
        return self._state.version

    @version.setter
    def version(self, value: str) -> None:
        self._state.version = value

    @property
    def infrastructure(self) -> Infrastructure:
        return self._state.infrastructure

    @property
    def id(self) -> str:
        return self._state.id

    @property
    def created_at(self) -> str:
        return self._state.created_at

    @property
    def last_opened_at(self) -> str:
        return self._state.last_opened_at

    @property
    def data_source_id(self) -> str:
        return self._state.data_source_id

    @property
    def data_source_kind(self) -> str:
        return self._state.data_source_kind

    @property
    def data_source_location(self) -> str:
        return self._state.data_source_location

    @property
    def data_source_config(self) -> Mapping[str, Any]:
        return MappingProxyType(self._state.data_source_config)

    @property
    def path(self) -> Path:
        return self._repository.path

    @property
    def secrets(self) -> AbstractSecretManager:
        return self._secrets

    @property
    def secret_manager_kind(self) -> str:
        return self._state.secret_manager_kind

    @property
    def secret_manager_service_uuid(self) -> str | None:
        return self._state.secret_manager_service_uuid

    @property
    def secret_manager_status(self) -> str:
        return "available" if self.secrets.is_working() else "unavailable"

    @property
    def active_secret_manager_name(self) -> str:
        if self.secret_manager_kind == "embedded":
            return "Embedded Project Storage"
        service_uuid = self.secret_manager_service_uuid
        service = (
            self.infrastructure.get_service_by_uuid(service_uuid)
            if service_uuid
            else None
        )
        if isinstance(service, AbstractSecretManagerService):
            return service.name
        return f"Missing service ({service_uuid or 'unknown'})"

    @classmethod
    def open(
        cls,
        path: str,
        password: str,
    ) -> "ProjectWorkspace":
        repository = SqlCipherRepository(path, password).open()
        return cls(repository, repository.load())

    @classmethod
    def create(
        cls,
        path: str,
        password: str,
    ) -> "ProjectWorkspace":
        repository = SqlCipherRepository.create(path, password)
        return cls(repository, repository.load())

    @classmethod
    def can_open(cls, path: str, password: str) -> bool:
        try:
            SqlCipherRepository(path, password).open()
            return True
        except Exception:
            return False

    def commit(self) -> None:
        self._state.touch()
        self._repository.save(self._state)

    def reload(self) -> "ProjectWorkspace":
        self._state = self._repository.load()
        self._secrets = self._resolve_secret_manager()
        return self

    def _resolve_secret_manager(self) -> AbstractSecretManager:
        if self._state.secret_manager_kind == "embedded":
            return self._embedded_secrets

        service_uuid = self._state.secret_manager_service_uuid
        if not service_uuid:
            return UnavailableSecretManager(
                "",
                "The project selects a service secret manager without a service UUID.",
            )
        service = self.infrastructure.get_service_by_uuid(service_uuid)
        if not isinstance(service, AbstractSecretManagerService):
            return UnavailableSecretManager(
                service_uuid,
                f"Selected secret-manager service {service_uuid} is unavailable.",
            )
        try:
            manager = service.get_secret_manager(self.infrastructure)
            if not manager.is_working():
                return UnavailableSecretManager(
                    service_uuid,
                    f"Selected secret-manager service {service.name} is unavailable.",
                )
            return manager
        except Exception as exc:
            return UnavailableSecretManager(
                service_uuid,
                f"Selected secret-manager service {service.name} is unavailable: {exc}",
            )

    def list_secret_managers(self) -> list[SecretManagerDescriptor]:
        descriptors = [
            SecretManagerDescriptor(
                id="embedded",
                name="Embedded Project Storage",
                kind="embedded",
                service_uuid=None,
                is_active=self.secret_manager_kind == "embedded",
                is_available=True,
                supports_keyfile_export=False,
                manager=self._embedded_secrets,
            )
        ]
        for service in self.infrastructure.services():
            if not isinstance(service, AbstractSecretManagerService):
                continue
            is_active = (
                self.secret_manager_kind == "service"
                and self.secret_manager_service_uuid == service.uuid
            )
            descriptors.append(
                SecretManagerDescriptor(
                    id=service.uuid,
                    name=service.name,
                    kind="service",
                    service_uuid=service.uuid,
                    is_active=is_active,
                    is_available=(
                        not isinstance(self._secrets, UnavailableSecretManager)
                        if is_active
                        else None
                    ),
                    supports_keyfile_export=(
                        self._secrets.supports_keyfile_export
                        if is_active
                        else False
                    ),
                    manager=self._secrets if is_active else None,
                    service=service,
                )
            )
        active_uuid = self.secret_manager_service_uuid
        if (
            self.secret_manager_kind == "service"
            and active_uuid
            and not any(item.service_uuid == active_uuid for item in descriptors)
        ):
            manager = UnavailableSecretManager(
                active_uuid,
                f"Selected secret-manager service {active_uuid} is unavailable.",
            )
            descriptors.append(
                SecretManagerDescriptor(
                    id=active_uuid,
                    name=f"Missing service ({active_uuid})",
                    kind="service",
                    service_uuid=active_uuid,
                    is_active=True,
                    is_available=False,
                    supports_keyfile_export=False,
                    manager=manager,
                )
            )
        return descriptors

    def probe_secret_manager(self, manager_id: str) -> SecretManagerDescriptor:
        if manager_id == "embedded":
            descriptor = SecretManagerDescriptor(
                id="embedded",
                name="Embedded Project Storage",
                kind="embedded",
                service_uuid=None,
                is_active=self.secret_manager_kind == "embedded",
                is_available=True,
                supports_keyfile_export=False,
                manager=self._embedded_secrets,
            )
        else:
            service = self.infrastructure.get_service_by_uuid(manager_id)
            if not isinstance(service, AbstractSecretManagerService):
                if (
                    self.secret_manager_kind == "service"
                    and self.secret_manager_service_uuid == manager_id
                ):
                    manager = UnavailableSecretManager(
                        manager_id,
                        f"Selected secret-manager service {manager_id} is unavailable.",
                    )
                    return SecretManagerDescriptor(
                        id=manager_id,
                        name=f"Missing service ({manager_id})",
                        kind="service",
                        service_uuid=manager_id,
                        is_active=True,
                        is_available=False,
                        supports_keyfile_export=False,
                        manager=manager,
                    )
                raise ValueError(f"Secret manager {manager_id} was not found.")
            try:
                manager = (
                    self._secrets
                    if self.secret_manager_service_uuid == manager_id
                    else service.get_secret_manager(self.infrastructure)
                )
            except Exception as exc:
                manager = UnavailableSecretManager(manager_id, str(exc))
            descriptor = SecretManagerDescriptor(
                id=manager_id,
                name=service.name,
                kind="service",
                service_uuid=manager_id,
                is_active=(
                    self.secret_manager_kind == "service"
                    and self.secret_manager_service_uuid == manager_id
                ),
                is_available=None,
                supports_keyfile_export=manager.supports_keyfile_export,
                manager=manager,
                service=service,
            )
        try:
            if descriptor.manager is None:
                raise RuntimeError(
                    f"Secret manager {manager_id} could not be initialized."
                )
            available = descriptor.manager.is_working()
        except Exception:
            available = False
        return SecretManagerDescriptor(
            id=descriptor.id,
            name=descriptor.name,
            kind=descriptor.kind,
            service_uuid=descriptor.service_uuid,
            is_active=descriptor.is_active,
            is_available=available,
            supports_keyfile_export=descriptor.supports_keyfile_export,
            manager=descriptor.manager,
            service=descriptor.service,
        )

    def _switch_secret_manager(
        self,
        target: AbstractSecretManager,
        *,
        kind: str,
        service_uuid: str | None,
        migrate: bool,
    ) -> OperationResult:
        if not target.is_working():
            return OperationResult(False, 16, "The selected secret manager is unavailable.")
        if (
            self.secret_manager_kind == kind
            and self.secret_manager_service_uuid == service_uuid
        ):
            return OperationResult(True, 0, "The selected secret manager is already active.")

        try:
            source_secrets = (
                self.secrets.list_secrets(keys_only=False) if migrate else {}
            )
            for name, value in source_secrets.items():
                target.save_secret(name, value)
            copied_keys = set(target.list_secrets(keys_only=True))
            missing = set(source_secrets) - copied_keys
            if missing:
                names = ", ".join(sorted(missing))
                return OperationResult(
                    False,
                    17,
                    f"Could not verify copied secrets: {names}.",
                )

            self._state.secret_manager_kind = kind
            self._state.secret_manager_service_uuid = service_uuid
            self.commit()
            self._secrets = target
            return OperationResult(True, 0, "Active secret manager updated.")
        except Exception as exc:
            self.reload()
            return OperationResult(False, 18, f"Could not switch secret manager: {exc}")

    def set_secret_manager(
        self,
        service_uuid: str,
        *,
        migrate: bool = True,
    ) -> OperationResult:
        service = self.infrastructure.get_service_by_uuid(service_uuid)
        if not isinstance(service, AbstractSecretManagerService):
            return OperationResult(False, 8, "Secret-manager service not found.")
        try:
            target = service.get_secret_manager(self.infrastructure)
        except Exception as exc:
            return OperationResult(False, 16, f"Secret manager is unavailable: {exc}")
        return self._switch_secret_manager(
            target,
            kind="service",
            service_uuid=service_uuid,
            migrate=migrate,
        )

    def use_embedded_secret_manager(
        self,
        *,
        migrate: bool = True,
    ) -> OperationResult:
        return self._switch_secret_manager(
            self._embedded_secrets,
            kind="embedded",
            service_uuid=None,
            migrate=migrate,
        )

    def import_secrets(self, manager: AbstractSecretManager | None) -> None:
        if manager is None or isinstance(manager, EmbeddedSecretManager):
            return
        for name, value in manager.list_secrets(keys_only=False).items():
            if name != "MLOX_CONFIG_INFRASTRUCTURE":
                self.secrets.save_secret(name, value)

    def _mutate(self, operation: Callable[[], OperationResult]) -> OperationResult:
        try:
            result = operation()
            if not result.success:
                self.reload()
                return result
            self.commit()
            return result
        except Exception as exc:
            self.reload()
            return OperationResult(False, 1, f"Operation failed: {exc}")

    @staticmethod
    def _load_config_from_path(path: str):
        stacks = get_stacks_path()
        service_dir, candidate = os.path.split(path)
        return load_config(stacks, service_dir, candidate)

    def project_created(self) -> OperationResult:
        result = project.create_project(self._state)
        if result.success:
            result.data = {"workspace": self}
        return result

    def list_servers(self) -> OperationResult:
        return servers.list_servers(self._state)

    def add_server(
        self,
        *,
        template_path: str,
        ip: str,
        port: int,
        root_user: str,
        root_password: str,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> OperationResult:
        return self._mutate(
            lambda: servers.add_server(
                self._state,
                self._load_config_from_path,
                template_path=template_path,
                ip=ip,
                port=port,
                root_user=root_user,
                root_password=root_password,
                extra_params=extra_params,
            )
        )

    def add_server_from_config(
        self,
        config: Any,
        params: Dict[str, str],
    ) -> OperationResult:
        return self._mutate(
            lambda: servers.add_server(
                self._state,
                lambda _: config,
                template_path=getattr(config, "path", config.id),
                ip=params.get("${MLOX_IP}", ""),
                port=int(params.get("${MLOX_PORT}", 0)),
                root_user=params.get("${MLOX_ROOT}", ""),
                root_password=params.get("${MLOX_ROOT_PW}", ""),
                extra_params=params,
            )
        )

    def setup_server(self, *, ip: str) -> OperationResult:
        return self._mutate(lambda: servers.setup_server(self._state, ip=ip))

    def check_server_health(self, *, ip: str) -> OperationResult:
        bundle = self.infrastructure.get_bundle_by_ip(ip)
        if not bundle:
            return OperationResult(False, 5, "Server not found in infrastructure.")
        return self._mutate(
            lambda: servers.check_server_health(bundle.server),
        )

    def teardown_server(self, *, ip: str) -> OperationResult:
        bundle = self.infrastructure.get_bundle_by_ip(ip)
        active_uuid = self.secret_manager_service_uuid
        if bundle and active_uuid and any(
            service.uuid == active_uuid for service in bundle.services
        ):
            return OperationResult(
                False,
                19,
                "Cannot remove the server hosting the active secret manager.",
            )
        return self._mutate(lambda: servers.teardown_server(self._state, ip=ip))

    def save_server_key(self, *, ip: str, output_path: str) -> OperationResult:
        return servers.save_server_key(
            self._state,
            save_to_json,
            self._repository.password,
            ip=ip,
            output_path=output_path,
        )

    def list_services(self) -> OperationResult:
        return services.list_services(self._state)

    def add_service(
        self,
        *,
        server_ip: str,
        template_id: str,
        params: Optional[Dict[str, str]] = None,
    ) -> OperationResult:
        return self._mutate(
            lambda: services.add_service(
                self._state,
                load_service_config_by_id,
                server_ip=server_ip,
                template_id=template_id,
                params=params,
            )
        )

    def add_service_from_config(
        self,
        config: Any,
        *,
        server_ip: str,
        params: Optional[Dict[str, str]] = None,
        service=None,
    ) -> OperationResult:
        return self._mutate(
            lambda: services.add_service(
                self._state,
                lambda _: config,
                server_ip=server_ip,
                template_id=config.id,
                params=params,
                service=service,
            )
        )

    def setup_service(self, *, name: str) -> OperationResult:
        return self._mutate(lambda: services.setup_service(self._state, name=name))

    def check_service_health(self, *, name: str) -> OperationResult:
        return self._mutate(
            lambda: services.check_service_health(self._state, name=name)
        )

    def teardown_service(self, *, name: str) -> OperationResult:
        service = self.infrastructure.get_service(name)
        if (
            service is not None
            and service.uuid == self.secret_manager_service_uuid
        ):
            return OperationResult(
                False,
                19,
                "Cannot remove the active secret manager. Select another one first.",
            )
        return self._mutate(lambda: services.teardown_service(self._state, name=name))

    def start_service(self, *, name: str) -> OperationResult:
        return self._mutate(lambda: services.start_service(self._state, name=name))

    def stop_service(self, *, name: str) -> OperationResult:
        return self._mutate(lambda: services.stop_service(self._state, name=name))

    def rename_service(self, *, name: str, new_name: str) -> OperationResult:
        return self._mutate(
            lambda: services.rename_service(
                self._state,
                name=name,
                new_name=new_name,
            )
        )

    def service_logs(
        self,
        *,
        name: str,
        label: Optional[str] = None,
        tail: int = 200,
    ) -> OperationResult:
        return services.service_logs(
            self._state,
            name=name,
            label=label,
            tail=tail,
        )

    def list_models(
        self,
        *,
        registry_name: Optional[str] = None,
    ) -> OperationResult:
        return models.list_models(self._state, registry_name=registry_name)

    def deploy_model(
        self,
        *,
        registry_name: Optional[str],
        model_name: str,
        model_version: str,
        server_ip: str,
        template_id: str = DEFAULT_MLSERVER_TEMPLATE_ID,
    ) -> OperationResult:
        return self._mutate(
            lambda: models.deploy_model(
                self._state,
                lambda current_project, **kwargs: services.add_service(
                    current_project,
                    load_service_config_by_id,
                    **kwargs,
                ),
                services.setup_service,
                registry_name=registry_name,
                model_name=model_name,
                model_version=model_version,
                server_ip=server_ip,
                template_id=template_id,
            )
        )

    @staticmethod
    def list_server_configs() -> OperationResult:
        return servers.list_server_configs(load_all_server_configs)

    @staticmethod
    def list_service_configs() -> OperationResult:
        return services.list_service_configs(load_all_service_configs)
