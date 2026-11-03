import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from typer.testing import CliRunner

from mlox import cli
from mlox.application.result import OperationResult
from mlox.application.use_cases import servers
from mlox.project import ProjectWorkspace
from tests.unit.test_server_exec import Connection, project_for


def key():
    return Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()


@pytest.fixture
def keys():
    return key(), key()


def run_update(home, public_key, remove=False):
    script = servers._AUTHORIZED_KEYS_SCRIPT
    script += f'\nPath.home = classmethod(lambda cls: Path({str(home)!r}))\n'
    script += f'update({public_key!r}, {tuple(public_key.split()[:2])!r}, {remove!r})'
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_authorized_keys_preserves_other_entries_and_matches_comments_and_options(tmp_path, keys):
    managed, client = keys
    directory = tmp_path / '.ssh'
    directory.mkdir()
    path = directory / 'authorized_keys'
    original = '# existing keys\n' + managed  # Also cover a missing trailing newline.
    path.write_text(original)
    assert run_update(tmp_path, client + ' client')['changed']
    assert path.read_text() == original + '\n' + client + ' client\n'
    assert not run_update(tmp_path, client + ' renamed')['changed']
    with path.open('a') as stream:
        stream.write('command="echo hello",no-pty ' + client + ' duplicate\n')
    assert run_update(tmp_path, client, True)['changed']
    assert path.read_text() == original + '\n'
    assert not run_update(tmp_path, client, True)['changed']
    assert path.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700


def test_key_comment_is_not_executed(tmp_path, keys):
    public_key = keys[0] + f' $(touch {tmp_path}/injected) `exit 1`'
    assert run_update(tmp_path, public_key)['changed']
    assert not (tmp_path / 'injected').exists()


def test_workspace_and_removal_protection(keys):
    managed, client = keys
    connection = Connection(SimpleNamespace(stdout='{"changed": true, "username": "mlox_test"}', exited=0))
    state = project_for(connection)
    state.infrastructure.get_bundle_by_ip('host').server.remote_user = SimpleNamespace(ssh_pub_key=managed)
    workspace = ProjectWorkspace.__new__(ProjectWorkspace)
    workspace._state = state
    assert workspace.add_server_ssh_key(ip='host', public_key=client).success
    assert workspace.remove_server_ssh_key(ip='host', public_key=client).success
    connection.run.reset_mock()
    assert not workspace.remove_server_ssh_key(ip='host', public_key=managed + ' new comment').success
    assert not workspace.add_server_ssh_key(ip='host', public_key=client + '\n' + managed).success
    assert not workspace.add_server_ssh_key(ip='missing', public_key=client).success
    assert not workspace.add_server_ssh_key(ip='host', public_key='ssh-ed25519 AAAA').success
    connection.run.assert_not_called()


def test_failure_and_missing_managed_identity(keys):
    connection = Connection(SimpleNamespace(stdout='', exited=1))
    state = project_for(connection)
    assert not servers.add_server_ssh_key(state, ip='host', public_key=keys[0]).success
    connection.run.reset_mock()
    assert not servers.remove_server_ssh_key(state, ip='host', public_key=keys[0]).success
    connection.run.assert_not_called()
    assert not servers.add_server_ssh_key(project_for(connection, set()), ip='host', public_key=keys[0]).success


@pytest.mark.parametrize('action', ['add', 'remove'])
def test_cli_forwards_key_and_reports_result(monkeypatch, keys, action):
    operation = Mock(return_value=OperationResult(True, 0, 'Updated.', {'changed': True, 'username': 'mlox_test'}))
    workspace = SimpleNamespace(**{f'{action}_server_ssh_key': operation})
    monkeypatch.setattr(ProjectWorkspace, 'open', Mock(return_value=workspace))
    result = CliRunner().invoke(cli.app, ['--output', 'json', 'server', f'{action}-ssh-key', '--project', 'project', '--password', 'pw', '--ip', 'host', '--public-key', keys[0]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['data']['changed']
    operation.assert_called_once_with(ip='host', public_key=keys[0])
