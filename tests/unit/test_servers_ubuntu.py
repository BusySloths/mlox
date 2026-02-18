from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from mlox.server import MloxUser, RemoteUser
from mlox.servers.ubuntu.docker import UbuntuDockerServer
from mlox.servers.ubuntu.k3s import UbuntuK3sServer
from mlox.servers.ubuntu.native import UbuntuNativeServer
from mlox.servers.ubuntu.simple import UbuntuSimpleServer


class FakeExec:
    def __init__(self):
        self.calls = []
        self.responses = {}
        self.file_reads = {}
        self.user_id = 1001

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def execute(self, conn, command, **kwargs):
        self._record("execute", command, **kwargs)
        return self.responses.get(command)

    def fs_set_permissions(self, conn, path, mode, **kwargs):
        self._record("fs_set_permissions", path, mode, **kwargs)

    def fs_find_and_replace(self, conn, path, old, new, **kwargs):
        self._record("fs_find_and_replace", path, old, new, **kwargs)

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_delete_dir(self, conn, path):
        self._record("fs_delete_dir", path)

    def fs_read_file(self, conn, path, format=None):
        self._record("fs_read_file", path, format)
        return self.file_reads.get(path, "")

    def fs_append_line(self, conn, path, line):
        self._record("fs_append_line", path, line)

    def sys_add_user(self, conn, name, pw, with_home_dir=True, sudoer=True):
        self._record(
            "sys_add_user",
            name,
            pw,
            with_home_dir=with_home_dir,
            sudoer=sudoer,
        )

    def sys_user_id(self, conn):
        self._record("sys_user_id")
        return self.user_id


def _server_conn(server):
    conn = SimpleNamespace(host=server.ip)

    def _run(command, warn=True):
        ok = "k3s-uninstall.sh" in command
        return SimpleNamespace(ok=ok)

    conn.run = _run

    @contextmanager
    def _cm():
        yield conn

    server.get_server_connection = lambda force_root=False: _cm()
    return conn


def _new_native_server() -> UbuntuNativeServer:
    return UbuntuNativeServer(
        ip="10.0.0.10",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-native",
    )


def _new_docker_server() -> UbuntuDockerServer:
    return UbuntuDockerServer(
        ip="10.0.0.11",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-docker",
    )


def test_ubuntu_native_setup_users_and_auth_toggles(monkeypatch):
    server = _new_native_server()
    fake_exec = FakeExec()
    server.exec = fake_exec
    _server_conn(server)

    server.mlox_user = MloxUser(
        name="mlox_user",
        pw="pw",
        home="/home/mlox_user",
        ssh_passphrase="mlox-pass",
    )
    monkeypatch.setattr(
        server, "get_remote_user_template", lambda: RemoteUser(ssh_passphrase="remote-pass")
    )
    monkeypatch.setattr(server, "test_connection", lambda: True)

    fake_exec.file_reads["/home/mlox_user/.ssh/id_rsa.pub"] = "ssh-rsa AAAA\n"
    fake_exec.file_reads["/home/mlox_user/.ssh/id_rsa"] = "-----BEGIN KEY-----\n"

    server.setup_users()
    assert server.remote_user is not None
    assert server.remote_user.ssh_pub_key.startswith("ssh-rsa")
    assert server.remote_user.ssh_key.startswith("-----BEGIN")
    assert server.mlox_user.uid == 1001

    server.disable_password_authentication()
    server.enable_password_authentication()
    names = [c[0] for c in fake_exec.calls]
    assert "fs_find_and_replace" in names
    assert "execute" in names


def test_ubuntu_native_server_info_and_git_ops(monkeypatch):
    server = _new_native_server()
    fake_exec = FakeExec()
    server.exec = fake_exec
    _server_conn(server)

    fake_exec.responses[
        """
                cpu_count=$(lscpu | grep "^CPU(s):" | awk '{print $2}')
                ram_gb=$(free -m | grep Mem | awk '{printf "%.0f", $2/1024}')
                storage_gb=$(df -h / | awk 'NR==2 {print $2}' | sed 's/G//')
                echo "$cpu_count,$ram_gb,$storage_gb"
            """
    ] = "8,16,120"
    fake_exec.responses["host 10.0.0.10"] = "10.0.0.10 has address 10.0.0.10."
    monkeypatch.setattr(
        "mlox.servers.ubuntu.native.sys_get_distro_info",
        lambda conn, ex: {"pretty_name": "Ubuntu", "version": "24.04"},
    )

    assert server.get_server_info(no_cache=False)["host"] == "Unknown"
    info = server.get_server_info(no_cache=True)
    assert info["cpu_count"] == 8.0
    assert info["pretty_name"] == "Ubuntu"
    assert server.get_backend_status()["backend.is_running"] is False

    server.setup_backend()
    assert server.get_backend_status()["backend.is_running"] is True
    server.start_backend_runtime()
    server.stop_backend_runtime()
    server.git_clone("https://github.com/org/repo.git", "/tmp/repo")
    server.git_pull("/tmp/repo")
    server.git_remove("/tmp/repo")
    server.teardown_backend()
    assert server.state == "no-backend"


def test_ubuntu_docker_backend_lifecycle_and_status(monkeypatch):
    server = _new_docker_server()
    fake_exec = FakeExec()
    server.exec = fake_exec
    _server_conn(server)
    monkeypatch.setattr(server, "_apt_wait", lambda conn: None)

    server.setup_backend()
    assert server.state == "running"

    fake_exec.responses["systemctl is-active docker"] = "active"
    fake_exec.responses["systemctl is-enabled docker"] = "enabled"
    fake_exec.responses["docker version --format '{{json .}}'"] = '{"Client":{"Version":"1"}}'
    fake_exec.responses["docker ps -a --format '{{json .}}'"] = '{"ID":"1"}\n{"ID":"2"}'
    status = server.get_backend_status()
    assert status["backend.is_running"] is True
    assert status["docker.is_enabled"] is True
    assert len(status["docker.containers"]) == 2

    fake_exec.responses["docker version --format '{{json .}}'"] = "{broken"
    bad = server.get_backend_status()
    assert bad["docker.version"] == "Error parsing version JSON"

    server.start_backend_runtime()
    server.stop_backend_runtime()
    server.teardown_backend()
    assert server.state == "no-backend"


def test_ubuntu_k3s_backend_paths():
    server = UbuntuK3sServer(
        ip="10.0.0.12",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-k3s",
        controller_url="https://controller:6443",
        controller_token="tok-123456",
    )
    fake_exec = FakeExec()
    server.exec = fake_exec
    _server_conn(server)

    server.setup_backend()
    assert "k3s-agent" in server.backend
    assert server.state == "running"

    fake_exec.responses["systemctl is-active k3s"] = "active"
    fake_exec.responses["systemctl is-active k3s-agent"] = None
    fake_exec.responses["cat /var/lib/rancher/k3s/server/node-token"] = "password: super-token"
    fake_exec.responses["kubectl get nodes -o wide"] = (
        "NAME  STATUS  ROLES\n"
        "node-1  Ready  control-plane\n"
    )
    info = server.get_backend_status()
    assert info["backend.is_running"] is True
    assert info["k3s.token"] == "super-token"
    assert isinstance(info["k3s.nodes"], list)

    server.start_backend_runtime()
    server.stop_backend_runtime()
    server.teardown_backend()
    assert server.state == "no-backend"


def test_ubuntu_simple_server_noops_and_debug(monkeypatch):
    server = UbuntuSimpleServer(
        ip="127.0.0.1",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-simple",
        root_private_key="key-material",
        root_passphrase="passphrase",
    )
    assert server.remote_user is not None
    assert server.remote_user.ssh_key == "key-material"

    called = {"setup_backend": 0}
    monkeypatch.setattr(server, "setup_backend", lambda: called.__setitem__("setup_backend", 1))
    server.setup()
    assert called["setup_backend"] == 1

    server.state = "running"
    server.setup()
    assert called["setup_backend"] == 1

    server.enable_debug_access()
    assert server.is_debug_access_enabled is True
    server.disable_debug_access()
    assert server.is_debug_access_enabled is False
    assert isinstance(server.get_backend_status(), dict)
