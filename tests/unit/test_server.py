import pytest
import os
import socket

from unittest.mock import patch, MagicMock
from mlox.server import (
    close_connection,
    open_connection,
    ServerConnection,
    AbstractServer,
    MloxUser,
    RemoteUser,
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
    def __init__(self):
        self.name = "/tmp/dummy"
        self.cleaned = False

    def cleanup(self):
        self.cleaned = True


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


@patch("mlox.server.Config")
@patch("mlox.server.Connection")
def test_open_connection_uses_password_auth(mock_connection, mock_config):
    mock_config.return_value = "fabric-config"
    mock_connection.return_value = "fabric-connection"

    conn, tmpdir = open_connection(
        {"host": "1.2.3.4", "user": "root", "pw": "pw", "port": 2222},
        timeout=7,
    )

    assert conn == "fabric-connection"
    assert tmpdir is None
    mock_config.assert_called_once_with(overrides={"sudo": {"password": "pw"}})
    mock_connection.assert_called_once_with(
        host="1.2.3.4",
        user="root",
        port=2222,
        connect_kwargs={"password": "pw"},
        config="fabric-config",
        connect_timeout=7,
    )


@patch("mlox.server.Config")
@patch("mlox.server.Connection")
def test_open_connection_uses_private_key_auth(mock_connection, mock_config):
    mock_config.return_value = "fabric-config"
    mock_connection.return_value = "fabric-connection"
    private_key = "-----BEGIN KEY-----\nsecret\n"

    conn, tmpdir = open_connection(
        {
            "host": "1.2.3.4",
            "user": "mlox",
            "pw": "pw",
            "port": "22",
            "private_key": private_key,
            "passphrase": "phrase",
        }
    )

    try:
        assert conn == "fabric-connection"
        assert tmpdir is not None
        key_filename = mock_connection.call_args.kwargs["connect_kwargs"][
            "key_filename"
        ]
        assert key_filename.startswith(tmpdir.name)
        with open(key_filename, encoding="utf-8") as key_file:
            assert key_file.read() == private_key
        assert oct(os.stat(key_filename).st_mode & 0o777) == "0o600"
        assert mock_connection.call_args.kwargs["connect_kwargs"] == {
            "key_filename": key_filename,
            "passphrase": "phrase",
        }
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()


def test_close_connection_closes_conn_and_tmpdir():
    conn = MagicMock()
    tmpdir = DummyTmpDir()

    close_connection(conn, tmpdir)

    conn.close.assert_called_once_with()
    assert tmpdir.cleaned is True


@patch("mlox.server.open_connection", side_effect=Exception("fail"))
@patch("mlox.server.close_connection", return_value=None)
def test_server_connection_failure(mock_close, mock_open):
    creds = {"host": "dummyhost", "user": "user", "pw": "pw"}
    conn = ServerConnection(creds, retries=0, retry_delay=0)
    with pytest.raises(Exception):
        with conn:
            pass


def test_server_connection_retries_transient_open_failure(monkeypatch):
    success_tmpdir = DummyTmpDir()
    good_conn = DummyConn()
    attempts = [
        socket.timeout("temporary"),
        (good_conn, success_tmpdir),
    ]
    closed = []

    def fake_open_connection(credentials):
        result = attempts.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr("mlox.server.open_connection", fake_open_connection)
    monkeypatch.setattr(
        "mlox.server.close_connection",
        lambda conn, tmpdir=None: closed.append((conn, tmpdir)),
    )
    monkeypatch.setattr("mlox.server.time.sleep", lambda seconds: None)

    with ServerConnection(
        {"host": "dummyhost", "user": "user", "pw": "pw", "port": 22},
        retries=1,
        retry_delay=0,
    ) as conn:
        assert conn is good_conn

    assert closed == [(good_conn, success_tmpdir)]


def test_server_connection_retries_socket_closed_during_verification(monkeypatch):
    failed_tmpdir = DummyTmpDir()
    success_tmpdir = DummyTmpDir()
    failed_conn = DummyConn()
    good_conn = DummyConn()
    attempts = [
        (failed_conn, failed_tmpdir),
        (good_conn, success_tmpdir),
    ]
    closed = []

    def fail_with_closed_socket(*args, **kwargs):
        raise OSError("Socket is closed")

    failed_conn.run = fail_with_closed_socket

    monkeypatch.setattr(
        "mlox.server.open_connection", lambda credentials: attempts.pop(0)
    )
    monkeypatch.setattr(
        "mlox.server.close_connection",
        lambda conn, tmpdir=None: closed.append((conn, tmpdir)),
    )
    monkeypatch.setattr("mlox.server.time.sleep", lambda seconds: None)

    with ServerConnection(
        {"host": "dummyhost", "user": "user", "pw": "pw", "port": 22},
        retries=1,
        retry_delay=0,
    ) as conn:
        assert conn is good_conn

    assert closed == [(None, failed_tmpdir), (good_conn, success_tmpdir)]


def test_server_connection_does_not_retry_non_retryable_error(monkeypatch):
    calls = []

    def fake_open_connection(credentials):
        calls.append(credentials)
        raise socket.gaierror("bad host")

    monkeypatch.setattr("mlox.server.open_connection", fake_open_connection)

    with pytest.raises(socket.gaierror):
        with ServerConnection(
            {"host": "badhost", "user": "user", "pw": "pw", "port": 22},
            retries=3,
            retry_delay=0,
        ):
            pass

    assert len(calls) == 1


def test_server_connection_cleans_up_when_verification_fails(monkeypatch):
    conn = DummyConn()
    tmpdir = DummyTmpDir()
    closed = []
    conn.run = lambda *args, **kwargs: MagicMock(
        ok=False,
        return_code=1,
        stderr="nope",
    )

    monkeypatch.setattr(
        "mlox.server.open_connection", lambda credentials: (conn, tmpdir)
    )
    monkeypatch.setattr(
        "mlox.server.close_connection",
        lambda close_conn, close_tmpdir=None: closed.append((close_conn, close_tmpdir)),
    )

    with pytest.raises(Exception):
        with ServerConnection(
            {"host": "dummyhost", "user": "user", "pw": "pw", "port": 22},
            retries=0,
            retry_delay=0,
        ):
            pass

    assert closed == [(None, tmpdir)]


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

    def firewall_up(self, ports):
        pass

    def firewall_down(self):
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


def test_get_server_connection_uses_root_credentials_by_default():
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="root-pw", service_config_id="svc"
    )

    conn = server.get_server_connection()

    assert conn.credentials == {
        "host": "1.2.3.4",
        "port": "22",
        "user": "root",
        "pw": "root-pw",
    }


def test_get_server_connection_uses_mlox_user_password_credentials():
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="root-pw", service_config_id="svc"
    )
    server.mlox_user = MloxUser(
        name="mlox",
        pw="mlox-pw",
        home="/home/mlox",
        ssh_passphrase="unused",
    )

    conn = server.get_server_connection()

    assert conn.credentials == {
        "host": "1.2.3.4",
        "port": "22",
        "user": "mlox",
        "pw": "mlox-pw",
    }


def test_get_server_connection_adds_remote_user_key_credentials():
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="root-pw", service_config_id="svc"
    )
    server.mlox_user = MloxUser(
        name="mlox",
        pw="mlox-pw",
        home="/home/mlox",
        ssh_passphrase="unused",
    )
    server.remote_user = RemoteUser(ssh_passphrase="phrase")
    server.remote_user.ssh_key = "private-key"
    server.remote_user.ssh_pub_key = "public-key"

    conn = server.get_server_connection()

    assert conn.credentials == {
        "host": "1.2.3.4",
        "port": "22",
        "user": "mlox",
        "pw": "mlox-pw",
        "public_key": "public-key",
        "private_key": "private-key",
        "passphrase": "phrase",
    }


def test_get_server_connection_force_root_ignores_mlox_and_remote_user():
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="root-pw", service_config_id="svc"
    )
    server.mlox_user = MloxUser(
        name="mlox",
        pw="mlox-pw",
        home="/home/mlox",
        ssh_passphrase="unused",
    )
    server.remote_user = RemoteUser(ssh_passphrase="phrase")
    server.remote_user.ssh_key = "private-key"
    server.remote_user.ssh_pub_key = "public-key"

    conn = server.get_server_connection(force_root=True)

    assert conn.credentials == {
        "host": "1.2.3.4",
        "port": "22",
        "user": "root",
        "pw": "root-pw",
    }


def test_create_new_task_executor_warns_on_os_mismatch(caplog):
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="root-pw", service_config_id="svc"
    )
    server.exec.supported_os_ids = "CustomOS"

    new_executor = server.create_new_task_executor()

    assert new_executor is not server.exec
    assert new_executor.supported_os_ids == "Ubuntu"
    assert "Task executor OS ID mismatch" in caplog.text


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


def test_test_connection_returns_false_on_error(monkeypatch):
    server = DummyServer(
        ip="1.2.3.4", root="root", root_pw="pw", service_config_id="svc"
    )

    def raise_connection_error(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(server, "get_server_connection", raise_connection_error)

    assert server.test_connection() is False
