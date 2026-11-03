from types import SimpleNamespace
import shlex
import shutil
import subprocess

import pytest
import yaml

from mlox.services.docker_proxy.docker import DockerProxyService
from mlox.utils import dataclass_to_dict, dict_to_dataclass


class Executor:
    def __init__(self):
        self.files = {}
        self.permissions = {}
        self.commands = []
        self.down = []
        self.fail = False

    def fs_create_dir(self, conn, path):
        pass

    def fs_set_permissions(self, conn, path, mode):
        self.permissions[path] = mode

    def fs_write_file(self, conn, path, content):
        self.files[path] = content

    def execute(self, conn, command, **kwargs):
        self.commands.append(command)
        if self.fail:
            return None
        _, _, src, dst = shlex.split(command)
        self.files[dst] = self.files.pop(src)
        return ''

    def docker_down(self, conn, compose, env, remove_volumes=False):
        self.down.append(remove_volumes)


def proxy():
    service = DockerProxyService(name='docker-proxy', service_config_id='docker-proxy-1-docker', template='docker_proxy/mlox.docker_proxy.yaml', target_path='/home/mlox/proxy')
    service.exec = Executor()
    service.setup(None)
    return service


def dynamic(service):
    return yaml.safe_load(service.exec.files[f'{service.target_path}/dynamic/routes.yaml'])


def test_setup_preserves_apps_and_owns_only_standard_ingress_ports():
    service = proxy()
    compose = yaml.safe_load(service.exec.files[f'{service.target_path}/docker-compose.yaml'])
    traefik = compose['services']['traefik']
    assert traefik['ports'] == ['80:80', '443:443']
    assert all('docker.sock' not in entry for entry in traefik['volumes'])
    assert 'host.docker.internal:host-gateway' in traefik['extra_hosts']
    service.teardown(None)
    assert service.exec.down == [False]


def test_compose_configuration_is_valid(tmp_path):
    if not shutil.which('docker'):
        pytest.skip('Docker Compose is not installed')
    service = proxy()
    compose = tmp_path / 'compose.yaml'
    compose.write_text(service.exec.files[f'{service.target_path}/docker-compose.yaml'])
    result = subprocess.run(['docker', 'compose', '-f', str(compose), 'config', '--quiet'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_add_remove_routes_is_atomic_and_per_route_tls():
    service = proxy()
    service.add_route(None, hostname='Notes.Example.org', backend='https://host.docker.internal:5230', tls_mode='letsencrypt', insecure_backend=True, backend_host='192.0.2.1')
    service.add_route(None, hostname='wiki.example.org', backend='http://host.docker.internal:3000')
    config = dynamic(service)
    assert len(config['http']['routers']) == 2
    router = next(r for r in config['http']['routers'].values() if 'notes.example.org' in r['rule'])
    assert router['tls']['certResolver'] == 'letsencrypt'
    assert len(config['http']['serversTransports']) == 1
    assert next(iter(config['http']['serversTransports'].values()))['insecureSkipVerify'] is True
    assert next(iter(config['http']['middlewares'].values()))['headers']['customRequestHeaders']['Host'] == '192.0.2.1'
    service.remove_route(None, hostname='notes.example.org')
    assert list(service.routes) == ['wiki.example.org']
    assert len(dynamic(service)['http']['routers']) == 1
    assert all(command.startswith('mv -f ') for command in service.exec.commands)


def test_invalid_and_failed_updates_preserve_previous_routes():
    service = proxy()
    service.add_route(None, hostname='wiki.example.org', backend='http://host.docker.internal:3000')
    previous = service.exec.files[f'{service.target_path}/dynamic/routes.yaml']
    with pytest.raises(ValueError):
        service.add_route(None, hostname='bad host', backend='http://host.docker.internal:3000')
    with pytest.raises(ValueError, match='already exists'):
        service.add_route(None, hostname='wiki.example.org', backend='http://host.docker.internal:3000')
    service.exec.fail = True
    with pytest.raises(RuntimeError):
        service.remove_route(None, hostname='wiki.example.org')
    assert list(service.routes) == ['wiki.example.org']
    assert service.exec.files[f'{service.target_path}/dynamic/routes.yaml'] == previous


@pytest.mark.parametrize('url', ['https://localhost:443', 'http://127.0.0.1:80', 'http://user:pw@example.com:80', 'file:///etc/passwd', 'http://host.docker.internal:80/path', 'http://host.docker.internal'])
def test_rejects_ambiguous_or_invalid_backend(url):
    service = proxy()
    with pytest.raises(ValueError):
        service.add_route(None, hostname='wiki.example.org', backend=url)


def test_project_round_trip_keeps_route_and_existing_runtime_names():
    service = proxy()
    service.add_route(None, hostname='wiki.example.org', backend='http://host.docker.internal:3000')
    service.exec = DockerProxyService.__dataclass_fields__['exec'].default_factory()
    restored = dict_to_dataclass(dataclass_to_dict(service))
    assert restored.routes == service.routes
    assert restored.target_path == service.target_path
    assert restored.compose_service_names == service.compose_service_names


def test_proxy_capability_lists_linked_services_without_exposing_mutable_state():
    from mlox.service import AbstractProxyService, ServiceCapability

    service = proxy()
    assert isinstance(service, AbstractProxyService)
    assert ServiceCapability.PROXY in service.capabilities
    service.add_route(None, hostname='wiki.example.org', backend='http://host.docker.internal:3000', service_uuid='wiki-uuid')
    assert service.list_relayed_services() == {'wiki-uuid'}
    routes = service.list_routes()
    routes['wiki.example.org']['backend'] = 'changed'
    assert service.routes['wiki.example.org']['backend'] != 'changed'


def test_proxy_template_has_semver_and_preserves_legacy_lookup():
    from mlox.config import load_service_config_by_id

    old = load_service_config_by_id('docker-proxy-1-docker')
    new = load_service_config_by_id('docker-proxy-1.0.0-docker')
    assert old and new and old.id == new.id == 'docker-proxy-1.0.0-docker'
    assert new.version == '1.0.0'
    assert new.name == 'Traefik Gateway'
    assert 'proxy' in new.service_capabilities()


def test_workspace_links_routes_to_existing_service():
    from contextlib import nullcontext
    from mlox.application.use_cases.docker_proxy import add_route

    service = proxy()
    service.state = 'running'
    bundle = SimpleNamespace(server=SimpleNamespace(get_server_connection=lambda: nullcontext(None)))
    infra = SimpleNamespace(get_service=lambda name: service, get_bundle_by_service=lambda item: bundle,
                            get_service_by_uuid=lambda uuid: object() if uuid == 'app-id' else None)
    project = SimpleNamespace(infrastructure=infra)
    result = add_route(project, name='docker-proxy', hostname='wiki.example.org',
                       backend='http://host.docker.internal:3000', service_uuid='app-id')
    assert result.success
    assert service.list_routes()['wiki.example.org']['service_uuid'] == 'app-id'
    bad = add_route(project, name='docker-proxy', hostname='bad.example.org',
                    backend='http://host.docker.internal:3000', service_uuid='missing')
    assert not bad.success and 'bad.example.org' not in service.routes


def test_managed_certificate_is_validated_before_route_mutation(monkeypatch):
    service = proxy()
    monkeypatch.setattr(service, '_tls_secret', lambda route, host: ('certificate', 'private-key'))
    service.add_route(None, hostname='wiki.example.org', backend='http://host.docker.internal:3000', tls_mode='managed', tls_secret_manager_uuid='manager', tls_secret_name='cert')
    config = dynamic(service)
    assert len(config['tls']['certificates']) == 1
    assert 'private-key' not in str(config)
    assert 'private-key' not in str(service.routes)
    assert '600' in service.exec.permissions.values()


def test_failed_project_commit_restores_runtime_routes():
    from contextlib import nullcontext
    from mlox.application.result import OperationResult
    from mlox.project.workspace import ProjectWorkspace

    service = proxy()
    service.state = 'running'
    bundle = SimpleNamespace(server=SimpleNamespace(get_server_connection=lambda: nullcontext(None)))
    infra = SimpleNamespace(get_service=lambda name: service, get_bundle_by_service=lambda candidate: bundle)
    workspace = object.__new__(ProjectWorkspace)
    workspace._state = SimpleNamespace(infrastructure=infra)

    def fail_commit(operation):
        result = operation()
        assert result.success
        return OperationResult(False, 1, 'Project save failed')

    workspace._mutate = fail_commit
    result = workspace.add_proxy_route(name='docker-proxy', hostname='wiki.example.org', backend='http://host.docker.internal:3000')
    assert not result.success
    assert service.routes == {}
    assert dynamic(service)['http']['routers'] == {}


def test_managed_certificate_secret_is_validated(monkeypatch):
    from tests.unit.services.test_mlflow_gateway_k3s_managed_tls import _tls_material
    from mlox.service import AbstractSecretManagerService, ServiceCapability

    material = _tls_material('wiki.example.org')

    class Provider(AbstractSecretManagerService):
        uuid = 'manager'
        capabilities = {ServiceCapability.SECRET_MANAGER}
        def get_secret_manager(self, infra):
            return SimpleNamespace(load_secret=lambda name: material)

    service = proxy()
    monkeypatch.setattr(service, 'get_dependent_service', lambda *args, **kwargs: Provider())
    service.add_route(None, hostname='wiki.example.org', backend='http://host.docker.internal:3000', tls_mode='managed', tls_secret_manager_uuid='manager', tls_secret_name='certificate')
    assert dynamic(service)['tls']['certificates']
    material['tls.hostname'] = 'other.example.org'
    with pytest.raises(ValueError, match='hostname'):
        service.add_route(None, hostname='second.example.org', backend='http://host.docker.internal:3001', tls_mode='managed', tls_secret_manager_uuid='manager', tls_secret_name='certificate')
    assert list(service.routes) == ['wiki.example.org']
