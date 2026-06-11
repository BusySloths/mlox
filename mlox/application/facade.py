"""Stateful application API for one loaded MLOX project."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from mlox.application.result import OperationResult
from mlox.application.use_cases import models, project, servers, services
from mlox.config import (
    get_stacks_path,
    load_all_server_configs,
    load_all_service_configs,
    load_config,
    load_service_config_by_id,
)
from mlox.session import ProjectSession
from mlox.utils import save_to_json

DEFAULT_MLSERVER_TEMPLATE_ID = "mlflow-mlserver-3.8.1-docker"


class ProjectApplication:
    """Application operations and commit boundary for one project session."""

    def __init__(self, session: ProjectSession) -> None:
        self.session = session

    @property
    def project(self):
        return self.session.project

    @property
    def secrets(self):
        return self.session.secrets

    @classmethod
    def open(
        cls,
        path: str,
        password: str,
    ) -> "ProjectApplication":
        return cls(ProjectSession.open(path, password))

    @classmethod
    def create(
        cls,
        path: str,
        password: str,
    ) -> "ProjectApplication":
        return cls(ProjectSession.create(path, password))

    @classmethod
    def from_session(cls, session: ProjectSession) -> "ProjectApplication":
        return cls(session)

    def reload(self):
        return self.session.reload()

    def _mutate(self, operation: Callable[[], OperationResult]) -> OperationResult:
        try:
            result = operation()
            if not result.success:
                self.session.reload()
                return result
            self.session.commit()
            return result
        except Exception as exc:
            self.session.reload()
            return OperationResult(False, 1, f"Operation failed: {exc}")

    @staticmethod
    def _load_config_from_path(path: str):
        stacks = get_stacks_path()
        service_dir, candidate = os.path.split(path)
        return load_config(stacks, service_dir, candidate)

    def project_created(self) -> OperationResult:
        return project.create_project(self.project)

    def list_servers(self) -> OperationResult:
        return servers.list_servers(self.project)

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
                self.project,
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
                self.project,
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
        return self._mutate(lambda: servers.setup_server(self.project, ip=ip))

    def teardown_server(self, *, ip: str) -> OperationResult:
        return self._mutate(lambda: servers.teardown_server(self.project, ip=ip))

    def save_server_key(self, *, ip: str, output_path: str) -> OperationResult:
        return servers.save_server_key(
            self.project,
            save_to_json,
            self.session.password,
            ip=ip,
            output_path=output_path,
        )

    def list_services(self) -> OperationResult:
        return services.list_services(self.project)

    def add_service(
        self,
        *,
        server_ip: str,
        template_id: str,
        params: Optional[Dict[str, str]] = None,
    ) -> OperationResult:
        return self._mutate(
            lambda: services.add_service(
                self.project,
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
                self.project,
                lambda _: config,
                server_ip=server_ip,
                template_id=config.id,
                params=params,
                service=service,
            )
        )

    def setup_service(self, *, name: str) -> OperationResult:
        return self._mutate(lambda: services.setup_service(self.project, name=name))

    def teardown_service(self, *, name: str) -> OperationResult:
        return self._mutate(lambda: services.teardown_service(self.project, name=name))

    def start_service(self, *, name: str) -> OperationResult:
        return self._mutate(lambda: services.start_service(self.project, name=name))

    def stop_service(self, *, name: str) -> OperationResult:
        return self._mutate(lambda: services.stop_service(self.project, name=name))

    def rename_service(self, *, name: str, new_name: str) -> OperationResult:
        return self._mutate(
            lambda: services.rename_service(
                self.project,
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
            self.project,
            name=name,
            label=label,
            tail=tail,
        )

    def list_models(
        self,
        *,
        registry_name: Optional[str] = None,
    ) -> OperationResult:
        return models.list_models(self.project, registry_name=registry_name)

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
                self.project,
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
