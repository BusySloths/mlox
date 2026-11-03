"""Verify delegated SSH access against the disposable Multipass server."""

from io import StringIO

import paramiko
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from fabric import Connection

from mlox.infra import Bundle
from mlox.project import ProjectWorkspace

pytestmark = pytest.mark.integration


def test_client_ssh_key_add_login_remove_and_managed_access(ubuntu_docker_server, tmp_path):
    server = ubuntu_docker_server
    workspace = ProjectWorkspace.create(str(tmp_path / "ssh-access.mlox"), "test-password")
    workspace.infrastructure.bundles.append(Bundle(name=server.ip, server=server))

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        Encoding.OpenSSH, PublicFormat.OpenSSH
    ).decode()
    client_key = paramiko.Ed25519Key.from_private_key(StringIO(
        private_key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()).decode()
    ))

    def client_login():
        # Every attempt creates a fresh connection, with no agent/password fallback.
        with Connection(
            host=server.ip,
            user=server.mlox_user.name,
            port=int(server.port),
            connect_timeout=10,
            connect_kwargs={
                "pkey": client_key,
                "allow_agent": False,
                "look_for_keys": False,
                "auth_timeout": 10,
            },
        ) as conn:
            return conn.run("whoami", hide=True, pty=False).stdout.strip()

    try:
        with pytest.raises(paramiko.AuthenticationException):
            client_login()

        added = workspace.add_server_ssh_key(
            ip=server.ip, public_key=public_key + " integration-client"
        )
        assert added.success, added.message
        assert added.data == {"changed": True, "username": server.mlox_user.name}
        assert client_login() == server.mlox_user.name

        duplicate = workspace.add_server_ssh_key(
            ip=server.ip, public_key=public_key + " renamed-comment"
        )
        assert duplicate.success, duplicate.message
        assert duplicate.data["changed"] is False

        protected = workspace.remove_server_ssh_key(
            ip=server.ip, public_key=server.remote_user.ssh_pub_key
        )
        assert not protected.success
        assert client_login() == server.mlox_user.name

        removed = workspace.remove_server_ssh_key(ip=server.ip, public_key=public_key)
        assert removed.success, removed.message
        assert removed.data["changed"] is True
        with pytest.raises(paramiko.AuthenticationException):
            client_login()

        absent = workspace.remove_server_ssh_key(ip=server.ip, public_key=public_key)
        assert absent.success, absent.message
        assert absent.data["changed"] is False

        with server.get_server_connection() as conn:
            assert conn.run("whoami", hide=True, pty=False).stdout.strip() == server.mlox_user.name
    finally:
        # The package-scoped server is shared with other integration tests.
        cleanup = workspace.remove_server_ssh_key(ip=server.ip, public_key=public_key)
        assert cleanup.success, cleanup.message
