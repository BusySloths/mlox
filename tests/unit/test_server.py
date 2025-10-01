import pytest
import logging
import socket

from unittest.mock import patch, MagicMock
from mlox.server import (
    ServerConnection,
    AbstractServer,
    MloxUser,
    RemoteUser,
    sys_get_distro_info,
)


class DummyConn:
    def __init__(self):
        self.opened = False
        self.host = "dummyhost"
        self.is_connected = True

    def open(self):
        self.opened = True

    def run(self, cmd, **kwargs):
        return MagicMock(ok=True, return_code=0, stderr="")


class DummyTmpDir:
    def cleanup(self):
        pass


@patch("mlox.server.open_connection", return_value=(DummyConn(), DummyTmpDir()))
@patch("mlox.server.close_connection", return_value=None)
def test_server_connection_success(mock_close, mock_open):
    creds = {"host": "dummyhost", "user": "user", "pw": "pw", "port": 22}
    conn = ServerConnection(creds, retries=1, retry_delay=0)
    with conn as c:
        assert getattr(
            c, "opened", True
        )  # DummyConn has .opened, fabric.Connection may not
        assert getattr(c, "host", "dummyhost") == "dummyhost"


@patch("mlox.remote.open_connection", side_effect=Exception("fail"))
@patch("mlox.remote.close_connection", return_value=None)
def test_server_connection_failure(mock_close, mock_open):
    creds = {"host": "dummyhost", "user": "user", "pw": "pw"}
    conn = ServerConnection(creds, retries=0, retry_delay=0)
    with pytest.raises(Exception):
        with conn:
            pass


@patch("mlox.server.fs_read_file", return_value='NAME="Ubuntu"\nVERSION_ID="22.04"')
def test_sys_get_distro_info_os_release(mock_fs):
    conn = DummyConn()
    info = sys_get_distro_info(conn)
    assert info["name"] == "Ubuntu"
    assert info["version"] == "22.04"


@patch("mlox.server.fs_read_file", side_effect=Exception("fail"))
@patch(
    "mlox.server.exec_command",
    return_value="Distributor ID: Ubuntu\nRelease: 22.04\nDescription: Ubuntu 22.04 LTS\nCodename: jammy",
)
def test_sys_get_distro_info_lsb_release(mock_exec, mock_fs):
    conn = DummyConn()
    info = sys_get_distro_info(conn)
    assert info["name"] == "Ubuntu"
    assert info["version"] == "22.04"
    assert info["pretty_name"] == "Ubuntu 22.04 LTS"
    assert info["codename"] == "jammy"


@patch("mlox.remote.fs_read_file", side_effect=Exception("fail"))
@patch("mlox.remote.exec_command", side_effect=Exception("fail"))
def test_sys_get_distro_info_failure(mock_exec, mock_fs):
    conn = DummyConn()
    info = sys_get_distro_info(conn)
    assert info is None


# AbstractServer cannot be instantiated directly, but we can test its templates
class DummyServer(AbstractServer):
    def setup(self):
        pass

    def update(self):
        pass

    def teardown(self):
        pass

    def get_server_info(self, no_cache=False):
        return {"info": 1}

    def enable_debug_access(self):
        pass

    def disable_debug_access(self):
        pass

    def setup_backend(self):
        pass

    def teardown_backend(self):
        pass

    def get_backend_status(self):
        return {"status": "ok"}

    def start_backend_runtime(self):
        pass

    def stop_backend_runtime(self):
        pass


def test_mlox_user_template():
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="pw", service_config_id="svc"
    )
    user = server.get_mlox_user_template()
    assert user.name.startswith("mlox_")
    assert user.pw
    assert user.home.startswith("/home/mlox_")


def test_remote_user_template():
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="pw", service_config_id="svc"
    )
    user = server.get_remote_user_template()
    assert user.ssh_passphrase


def test_test_connection(monkeypatch):
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="pw", service_config_id="svc"
    )

    class DummyConn:
        is_connected = True

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(server, "get_server_connection", lambda *a, **kw: DummyConn())
    assert server.test_connection() is True
