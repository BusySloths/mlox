from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from mlox.operations import OperationResult

class SessionRepositoryPort(Protocol):
    def load(self, project: str, password: str) -> OperationResult: ...

class ConfigCatalogPort(Protocol):
    def load_server(self, template_path: str): ...
    def load_service(self, template_id: str): ...

@dataclass
class ListServersUseCase:
    sessions: SessionRepositoryPort
    def execute(self, project: str, password: str) -> OperationResult:
        result = self.sessions.load(project, password)
        if not result.success:
            return result
        session = result.data
        servers = []
        for bundle in session.infra.bundles:
            servers.append({
                'ip': bundle.server.ip,
                'state': getattr(bundle.server, 'state', 'unknown'),
                'service_count': len(bundle.services),
                'service_config_id': getattr(bundle.server, 'service_config_id', None),
                'port': getattr(bundle.server, 'port', None),
                'discovered': getattr(bundle.server, 'discovered', None),
                'backend': getattr(bundle.server, 'backend', None) or [],
            })
        return OperationResult(True,0,'No servers found.' if not servers else 'Servers retrieved successfully.', {'servers': servers})

@dataclass
class AddServerUseCase:
    sessions: SessionRepositoryPort
    catalog: ConfigCatalogPort
    def execute(self, project: str, password: str, *, template_path: str, ip: str, port: int, root_user: str, root_password: str, extra_params: Optional[Dict[str,str]] = None) -> OperationResult:
        result = self.sessions.load(project,password)
        if not result.success:
            return result
        config = self.catalog.load_server(template_path)
        if config is None:
            return OperationResult(False,3,'Server template not found.')
        session = result.data
        params = {'${MLOX_IP}': ip, '${MLOX_PORT}': str(port), '${MLOX_ROOT}': root_user, '${MLOX_ROOT_PW}': root_password}
        if extra_params: params.update(extra_params)
        bundle = session.infra.add_server(config=config, params=params)
        if not bundle:
            return OperationResult(False,4,'Failed to add server to the project infrastructure.')
        session.save_infrastructure()
        return OperationResult(True,0,f'Added server {ip}.', {'bundle': bundle})
