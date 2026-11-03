from types import SimpleNamespace
import subprocess
import shutil
from pathlib import Path

import pytest
import yaml

from mlox.config import load_service_config_by_id
from mlox.services.catalog_apps.docker import CatalogAppDockerService
from mlox.utils import dataclass_to_dict, dict_to_dataclass


def test_catalog_descriptors_use_shared_prefix():
    root = Path(__file__).resolve().parents[3] / 'mlox/services/catalog_apps'
    descriptors = list(root.glob('mlox.*.yaml'))
    assert descriptors
    for descriptor in descriptors:
        assert descriptor.name.startswith('mlox.catalog_app.')
        config = yaml.safe_load(descriptor.read_text())
        assert config['id'].startswith('catalog-app-')
        assert config['name'].startswith('Application: ')
        assert config['build']['params']['name'].startswith('app-')
        assert 'health' in config['capabilities']['service']
        assert 'app' in config['capabilities']['service']
        assert all(url.startswith('https://') for url in config['links'].values())


class FakeExecutor:
    def __init__(self):
        self.files = {}
        self.modes = {}
        self.down = []

    def fs_create_dir(self, conn, path):
        pass

    def fs_set_permissions(self, conn, path, mode):
        self.modes[path] = mode

    def fs_write_file(self, conn, path, content):
        self.files[path] = content

    def docker_down(self, conn, path, env, remove_volumes=False):
        self.down.append(remove_volumes)


def make_app(config_id, **params):
    config = load_service_config_by_id(config_id)
    values = {'${MLOX_USER_HOME}': '/home/mlox', '${MLOX_AUTO_PORT_WEB_UI}': '14443', '${MLOX_AUTO_PW}': 'valid-password'}
    values.update(params)
    app = config.instantiate_service(values)
    app.exec = FakeExecutor()
    return app


@pytest.mark.parametrize('config_id', ['catalog-app-memos-0.31.0-docker', 'catalog-app-etherpad-2.6.1-docker', 'catalog-app-wikijs-2.5.306-docker', 'catalog-app-roundcube-1.6.11-docker'])
def test_packaged_compose_renders_and_preserves_volumes(config_id, tmp_path):
    app = make_app(config_id, **{'${APP_IMAP_SERVER}': 'ssl://mail.example.org', '${APP_SMTP_SERVER}': 'tls://mail.example.org'})
    app.setup(SimpleNamespace(host='192.0.2.1'))
    compose = yaml.safe_load(app.exec.files[f'{app.target_path}/docker-compose.yaml'])
    assert compose['services']['traefik']['ports'] == ['14443:443']
    assert all('docker.sock' not in mount for mount in compose['services']['traefik']['volumes'])
    assert 'ports' not in compose['services']['app']
    assert app.exec.modes[app.target_path] == '700'
    for name in ('docker-compose.yaml', 'service.env', 'dynamic.yaml'):
        (tmp_path / name).write_text(app.exec.files[f'{app.target_path}/{name}'])
    if shutil.which('docker'):
        result = subprocess.run(['docker', 'compose', '--env-file', str(tmp_path / 'service.env'), '-f', str(tmp_path / 'docker-compose.yaml'), 'config', '--quiet'], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    app.spin_down(None)
    app.teardown(None)
    assert app.exec.down == [False, False]


def test_distinct_installations_and_persisted_path():
    first, second = make_app('catalog-app-memos-0.31.0-docker'), make_app('catalog-app-memos-0.31.0-docker')
    assert first.target_path != second.target_path
    # The project serializer restores the original path after construction.
    first.exec = CatalogAppDockerService.__dataclass_fields__['exec'].default_factory()
    restored = dict_to_dataclass(dataclass_to_dict(first))
    assert restored.target_path == first.target_path
    assert 'app' in restored.capabilities


def test_existing_catalog_app_displays_as_app_after_rename():
    from mlox.tui.screens.dashboard.tree import service_tree_label

    app = make_app('catalog-app-memos-0.31.0-docker')
    app.name = 'My notes'
    assert service_tree_label(app) == 'App: My notes'


def test_application_group_maps_to_app_capability():
    from mlox.config import _capabilities_from_groups

    assert _capabilities_from_groups({'application': None})['service'] == {'app'}


def test_managed_certificate_is_validated_and_private(monkeypatch):
    app = make_app('catalog-app-memos-0.31.0-docker', **{'${APP_TLS_MODE}': 'managed', '${APP_TLS_SECRET_NAME}': 'cert', '${APP_TLS_SECRET_MANAGER_UUID}': 'manager'})
    monkeypatch.setattr(app, '_load_secret', lambda: {'tls.hostname': 'notes.example.org', 'tls.crt': 'cert', 'tls.key': 'key'})
    monkeypatch.setattr('mlox.services.catalog_apps.docker._validate_certificate', lambda cert, key, host: None)
    app.setup(SimpleNamespace(host='192.0.2.1'))
    assert app.exec.files[f'{app.target_path}/tls.key'] == 'key'
    assert app.exec.modes[f'{app.target_path}/tls.key'] == '600'
    assert app.service_urls['Web UI'] == 'https://notes.example.org:14443'
    assert 'key' not in str(dataclass_to_dict(app))


def test_letsencrypt_http_challenge_only_requires_hostname():
    app = make_app('catalog-app-memos-0.31.0-docker', **{'${APP_TLS_MODE}': 'letsencrypt', '${APP_HOSTNAME}': 'notes.example.org'})
    app.setup(SimpleNamespace(host='192.0.2.1'))
    proxy = yaml.safe_load(app.exec.files[f'{app.target_path}/docker-compose.yaml'])['services']['traefik']
    assert '80:80' in proxy['ports']
    assert '--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web' in proxy['command']
    assert app.service_ports['ACME HTTP'] == 80


@pytest.mark.parametrize('code, expected', [('200', 'running'), ('302', 'running'), ('502', 'error'), ('', 'error')])
def test_health_requires_http_response_through_proxy(code, expected):
    app = make_app('catalog-app-memos-0.31.0-docker')
    app.setup(SimpleNamespace(host='192.0.2.1'))
    app.exec.docker_service_state = lambda conn, container: 'running'
    app.exec.execute = lambda conn, command, **kwargs: code
    health = app.get_health(None)
    assert health['status'] == expected
    assert health['healthy'] is (expected == 'running')


def test_managed_tls_rejects_invalid_certificate_before_writes(monkeypatch):
    app = make_app('catalog-app-memos-0.31.0-docker', **{'${APP_TLS_MODE}': 'managed', '${APP_TLS_SECRET_NAME}': 'cert', '${APP_TLS_SECRET_MANAGER_UUID}': 'manager'})
    monkeypatch.setattr(app, '_load_secret', lambda: {'tls.hostname': 'notes.example.org', 'tls.crt': 'invalid', 'tls.key': 'invalid'})
    with pytest.raises(ValueError, match='PEM'):
        app.setup(SimpleNamespace(host='192.0.2.1'))
    assert not app.exec.files


def test_roundcube_requires_mail_hosts_before_writes():
    app = make_app('catalog-app-roundcube-1.6.11-docker')
    with pytest.raises(ValueError, match='IMAP and SMTP'):
        app.setup(SimpleNamespace(host='192.0.2.1'))
    assert not app.exec.files
