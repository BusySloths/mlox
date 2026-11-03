"""Independent shared Traefik service with explicit live HTTP routes."""
from __future__ import annotations

import hashlib
import ipaddress
import re
import shlex
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import yaml

from mlox.execution import TaskGroup
from mlox.service import AbstractHealthService, AbstractProxyService, AbstractSecretManagerService, AbstractService, ServiceCapability, service_health_payload
from mlox.services.mlflow_gateway.k3s_managed_tls import _valid_hostname, _validate_certificate


def _hostname(value: str) -> str:
    host = str(value).strip().lower().rstrip('.')
    if not _valid_hostname(host):
        raise ValueError('Enter a valid hostname, such as app.example.org.')
    return host


def _backend(value: str) -> str:
    value = str(value).strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Backend URL has an invalid port or host.') from exc
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment or
            port is None or not 1 <= port <= 65535):
        raise ValueError('Backend must be an HTTP(S) URL with an explicit port and no path or credentials.')
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
            raise ValueError('Invalid backend hostname.')
    if host in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('localhost refers to the proxy container; use host.docker.internal for host-published ports.')
    return value.rstrip('/')


@dataclass
class DockerProxyService(AbstractService, AbstractHealthService, AbstractProxyService):
    """One Traefik container; routes are stored in project state and watched files."""

    capabilities = {ServiceCapability.HEALTH, ServiceCapability.PROXY}
    routes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        if not re.search(r'-[0-9a-f]{32}$', self.target_path):
            self.target_path = f'{self.target_path}-{self.uuid}'
        self.service_ports.update({'HTTP': 80, 'HTTPS': 443})
        self.compose_service_names = {'Traefik': f'mlox-docker-proxy-{self.uuid}'}

    def _tls_secret(self, route: dict[str, Any], hostname: str) -> tuple[str, str]:
        manager_id, name = route.get('tls_secret_manager_uuid', ''), route.get('tls_secret_name', '')
        if not manager_id or not name:
            raise ValueError('Managed TLS requires a secret-manager UUID and secret name.')
        provider = self.get_dependent_service(manager_id, required_type=AbstractSecretManagerService, required_capabilities={ServiceCapability.SECRET_MANAGER})
        if not isinstance(provider, AbstractSecretManagerService):
            raise ValueError('TLS secret-manager service is unavailable.')
        secret = provider.get_secret_manager(self._service_lookup).load_secret(name)
        if not isinstance(secret, dict):
            raise ValueError('TLS secret must contain tls.hostname, tls.crt and tls.key.')
        secret_hostname = _hostname(secret.get('tls.hostname', ''))
        cert, key = secret.get('tls.crt'), secret.get('tls.key')
        if secret_hostname != hostname or not isinstance(cert, str) or not isinstance(key, str):
            raise ValueError('TLS secret hostname must match the route and include tls.crt and tls.key.')
        _validate_certificate(cert, key, hostname)
        return cert, key

    def _render(self, routes: dict[str, dict[str, Any]]) -> tuple[str, dict[str, str]]:
        dynamic: dict[str, Any] = {'http': {'routers': {}, 'services': {}, 'serversTransports': {}, 'middlewares': {}}}
        files: dict[str, str] = {}
        certificates = []
        for host, raw in sorted(routes.items()):
            host = _hostname(host)
            route = dict(raw)
            backend = _backend(route.get('backend', ''))
            mode = route.get('tls_mode', 'self-signed')
            if mode not in {'self-signed', 'letsencrypt', 'managed'}:
                raise ValueError('Public TLS must be self-signed, letsencrypt or managed.')
            insecure = route.get('insecure_backend', False)
            if not isinstance(insecure, bool):
                raise ValueError('insecure_backend must be true or false.')
            if insecure and not backend.startswith('https://'):
                raise ValueError('Backend TLS verification applies only to HTTPS backends.')
            backend_host = str(route.get('backend_host', '')).strip()
            if backend_host and not re.fullmatch(r'[A-Za-z0-9.:-]+', backend_host):
                raise ValueError('Invalid backend Host header.')
            key = 'route-' + hashlib.sha256(host.encode()).hexdigest()[:20]
            router: dict[str, Any] = {'rule': f'Host(`{host}`)', 'entryPoints': ['websecure'], 'service': key, 'tls': {}}
            if mode == 'letsencrypt':
                router['tls'] = {'certResolver': 'letsencrypt'}
            if mode == 'managed':
                cert, private_key = self._tls_secret(route, host)
                version = hashlib.sha256((cert + private_key).encode()).hexdigest()
                cert_name, key_name = f'{version}.crt', f'{version}.key'
                files[cert_name], files[key_name] = cert, private_key
                certificates.append({'certFile': f'/config/{cert_name}', 'keyFile': f'/config/{key_name}'})
            service: dict[str, Any] = {'loadBalancer': {'servers': [{'url': backend}]}}
            if insecure:
                transport = key + '-transport'
                dynamic['http']['serversTransports'][transport] = {'insecureSkipVerify': True}
                service['loadBalancer']['serversTransport'] = transport
            if backend_host:
                middleware = key + '-host'
                dynamic['http']['middlewares'][middleware] = {'headers': {'customRequestHeaders': {'Host': backend_host}}}
                router['middlewares'] = [middleware]
            dynamic['http']['routers'][key] = router
            dynamic['http']['services'][key] = service
        if certificates:
            dynamic['tls'] = {'certificates': certificates}
        return yaml.safe_dump(dynamic, sort_keys=False), files

    def _write_configuration(self, conn, routes):
        content, secrets = self._render(routes)  # Validate everything before writing.
        directory = f'{self.target_path}/dynamic'
        for name, value in secrets.items():
            path = f'{directory}/{name}'
            self.exec.fs_write_file(conn, path, value)
            self.exec.fs_set_permissions(conn, path, '600')
        temporary = f'{directory}/routes-{uuid.uuid4().hex}.tmp'
        self.exec.fs_write_file(conn, temporary, content)
        self.exec.fs_set_permissions(conn, temporary, '600')
        command = f'mv -f {shlex.quote(temporary)} {shlex.quote(directory + "/routes.yaml")}'
        if self.exec.execute(conn, command, group=TaskGroup.FILESYSTEM) is None:
            raise RuntimeError('Could not apply proxy routes.')

    def setup(self, conn):
        # Validate routes before changing the server.
        self._render(self.routes)
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_set_permissions(conn, self.target_path, '700')
        for directory in ('dynamic', 'acme'):
            path = f'{self.target_path}/{directory}'
            self.exec.fs_create_dir(conn, path)
            self.exec.fs_set_permissions(conn, path, '700')
        compose = {'services': {'traefik': {
            'image': 'traefik:v3.3.7', 'container_name': self.compose_service_names['Traefik'],
            'restart': 'unless-stopped', 'ports': ['80:80', '443:443'],
            'extra_hosts': ['host.docker.internal:host-gateway'],
            'command': ['--providers.file.directory=/config', '--providers.file.watch=true',
                        '--entrypoints.web.address=:80', '--entrypoints.websecure.address=:443',
                        '--entrypoints.web.http.redirections.entrypoint.to=websecure',
                        '--entrypoints.web.http.redirections.entrypoint.scheme=https',
                        '--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web',
                        '--certificatesresolvers.letsencrypt.acme.storage=/acme/acme.json'],
            'volumes': ['./dynamic:/config:ro', './acme:/acme'],
        }}}
        self.exec.fs_write_file(conn, f'{self.target_path}/{self.target_docker_script}', yaml.safe_dump(compose, sort_keys=False))
        self.exec.fs_write_file(conn, f'{self.target_path}/{self.target_docker_env}', '')
        self._write_configuration(conn, self.routes)
        self.state = 'starting'

    def add_route(self, conn, *, hostname: str, backend: str, tls_mode: str = 'self-signed', insecure_backend: bool = False, backend_host: str = '', tls_secret_manager_uuid: str = '', tls_secret_name: str = '', service_uuid: str = '') -> None:
        host = _hostname(hostname)
        if host in self.routes:
            raise ValueError(f'A route for {host} already exists.')
        routes = dict(self.routes)
        routes[host] = {'backend': _backend(backend), 'tls_mode': tls_mode, 'insecure_backend': insecure_backend, 'backend_host': backend_host, 'tls_secret_manager_uuid': tls_secret_manager_uuid, 'tls_secret_name': tls_secret_name, 'service_uuid': service_uuid}
        self._write_configuration(conn, routes)
        self.routes = routes

    def remove_route(self, conn, *, hostname: str) -> None:
        host = _hostname(hostname)
        if host not in self.routes:
            raise ValueError(f'No route exists for {host}.')
        routes = dict(self.routes)
        del routes[host]
        self._write_configuration(conn, routes)
        self.routes = routes

    def list_routes(self) -> dict[str, dict[str, Any]]:
        return {hostname: dict(route) for hostname, route in self.routes.items()}

    def spin_up(self, conn):
        return self.compose_up(conn)

    def spin_down(self, conn):
        self.exec.docker_down(conn, f'{self.target_path}/{self.target_docker_script}', f'{self.target_path}/{self.target_docker_env}', remove_volumes=False)
        self.state = 'stopped'
        return True

    def teardown(self, conn):
        self.spin_down(conn)
        self.state = 'un-initialized'

    def check(self, conn):
        state = str(self.exec.docker_service_state(conn, self.compose_service_names['Traefik']) or '').strip().lower()
        status = 'running' if state == 'running' else 'stopped' if state in {'exited', 'stopped', 'dead'} else 'unknown'
        self.state = status
        return {'status': status, 'container': state, 'routes': len(self.routes)}

    def get_health(self, conn):
        return service_health_payload(self, self.check(conn))

    def get_secrets(self):
        return {}
