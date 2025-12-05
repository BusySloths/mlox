import pytest

# Mark this module as an integration test
pytestmark = pytest.mark.integration


def test_simple_server_access_via_ssh_key(ubuntu_simple_server):
    assert ubuntu_simple_server.remote_user is not None

    with ubuntu_simple_server.get_server_connection() as conn:
        whoami = conn.run("whoami", hide=True, warn=True, pty=False)

    assert whoami.stdout.strip() == ubuntu_simple_server.root


def test_simple_server_debug_access_with_password(ubuntu_simple_server):
    assert not ubuntu_simple_server.is_debug_access_enabled

    ubuntu_simple_server.enable_debug_access()
    assert ubuntu_simple_server.is_debug_access_enabled

    with ubuntu_simple_server.get_server_connection(force_root=False) as conn:
        echoed = conn.run("echo debug-access-ok", hide=True, warn=True, pty=False)

    assert echoed.stdout.strip() == "debug-access-ok"

    ubuntu_simple_server.disable_debug_access()
    assert not ubuntu_simple_server.is_debug_access_enabled
