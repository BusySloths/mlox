from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from mlox.server import MloxUser, RemoteUser, ServerCapability
from mlox.servers.ubuntu.docker import UbuntuDockerServer
from mlox.servers.ubuntu.k3s import UbuntuK3sServer
from mlox.servers.ubuntu.native import UbuntuNativeServer
from mlox.servers.ubuntu.simple import UbuntuSimpleServer
from mlox.view.servers.ubuntu.native import (
    _collect_firewall_port_rows,
    _collect_firewall_ports,
    _filter_firewall_port_rows,
    _firewall_status_message,
    _is_firewall_up,
    _parse_firewall_open_ports,
)


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

    def firewall_up(self, conn, ports, source_ips_by_port=None):
        self._record("firewall_up", tuple(ports), source_ips_by_port)

    def firewall_down(self, conn):
        self._record("firewall_down")

    def firewall_status(self, conn):
        self._record("firewall_status")
        return "Status: active"

    def firewall_update(self, conn, ports, source_ips_by_port=None):
        self._record("firewall_update", tuple(ports), source_ips_by_port)


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


def test_ubuntu_server_capabilities():
    assert UbuntuNativeServer.capabilities == {
        ServerCapability.GIT,
        ServerCapability.FIREWALL,
        ServerCapability.INITIAL_AUTH_PASSWORD,
        ServerCapability.NATIVE,
    }
    assert UbuntuDockerServer.capabilities == {
        ServerCapability.GIT,
        ServerCapability.FIREWALL,
        ServerCapability.INITIAL_AUTH_PASSWORD,
        ServerCapability.DOCKER,
    }
    assert UbuntuK3sServer.capabilities == {
        ServerCapability.GIT,
        ServerCapability.FIREWALL,
        ServerCapability.INITIAL_AUTH_PASSWORD,
        ServerCapability.KUBERNETES,
    }
    assert UbuntuSimpleServer.capabilities == {ServerCapability.NATIVE}


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
        server,
        "get_remote_user_template",
        lambda: RemoteUser(ssh_passphrase="remote-pass"),
    )
    monkeypatch.setattr(server, "test_connection", lambda: True)

    fake_exec.file_reads["/home/mlox_user/.ssh/id_rsa.pub"] = "ssh-rsa AAAA\n"
    fake_exec.file_reads["/home/mlox_user/.ssh/id_rsa"] = "-----BEGIN KEY-----\n"

    server.setup_users()
    assert server.remote_user is not None
    assert server.remote_user.ssh_pub_key.startswith("ssh-rsa")
    assert server.remote_user.ssh_key.startswith("-----BEGIN")
    assert server.remote_user.ssh_key.endswith("\n")
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
    fake_exec.sys_get_distro_info = lambda conn: {
        "pretty_name": "Ubuntu",
        "version": "24.04",
    }

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
    fake_exec.responses["docker version --format '{{json .}}'"] = (
        '{"Client":{"Version":"1"}}'
    )
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

    fake_exec.responses["systemctl is-active k3s || true"] = "active"
    fake_exec.responses["systemctl is-active k3s-agent || true"] = "inactive"
    fake_exec.responses["cat /var/lib/rancher/k3s/server/node-token"] = (
        "password: super-token"
    )
    fake_exec.responses["kubectl get nodes -o wide"] = (
        "NAME  STATUS  ROLES\n" "node-1  Ready  control-plane\n"
    )
    info = server.get_backend_status()
    assert info["backend.is_running"] is True
    assert info["k3s.token"] == "super-token"
    assert isinstance(info["k3s.nodes"], list)

    server.start_backend_runtime()
    server.stop_backend_runtime()
    server.teardown_backend()
    assert server.state == "no-backend"


def test_ubuntu_k3s_agent_status_does_not_fetch_controller_node_info():
    server = UbuntuK3sServer(
        ip="10.0.0.13",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-k3s",
        controller_url="https://controller:6443",
        controller_token="tok-123456",
    )
    fake_exec = FakeExec()
    server.exec = fake_exec
    _server_conn(server)

    fake_exec.responses["systemctl is-active k3s || true"] = "inactive"
    fake_exec.responses["systemctl is-active k3s-agent || true"] = "active"

    info = server.get_backend_status()

    assert info["backend.is_running"] is True
    assert info["k3s.is_running"] is False
    assert info["k3s-agent.is_running"] is True
    assert "k3s.nodes" not in info
    commands = [args[0] for name, args, _ in fake_exec.calls if name == "execute"]
    assert "cat /var/lib/rancher/k3s/server/node-token" not in commands
    assert "kubectl get nodes -o wide" not in commands


def test_ubuntu_k3s_node_info_does_not_depend_on_token_output():
    server = UbuntuK3sServer(
        ip="10.0.0.14",
        root="root",
        root_pw="pw",
        service_config_id="ubuntu-k3s",
    )
    fake_exec = FakeExec()
    server.exec = fake_exec
    _server_conn(server)

    fake_exec.responses["systemctl is-active k3s || true"] = "active"
    fake_exec.responses["systemctl is-active k3s-agent || true"] = "inactive"
    fake_exec.responses["cat /var/lib/rancher/k3s/server/node-token"] = None
    fake_exec.responses["kubectl get nodes -o wide"] = (
        "NAME  STATUS  ROLES\n" "node-1  Ready  control-plane\n"
    )

    info = server.get_backend_status()

    assert "k3s.token" not in info
    assert info["k3s.nodes"] == [
        {"NAME": "node-1", "STATUS": "Ready", "ROLES": "control-plane"}
    ]


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
    monkeypatch.setattr(
        server, "setup_backend", lambda: called.__setitem__("setup_backend", 1)
    )
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


def test_ubuntu_native_firewall_calls_and_port_collection():
    server = _new_native_server()
    fake_exec = FakeExec()
    server.exec = fake_exec
    _server_conn(server)

    class DummyService:
        def __init__(self, ports):
            self.service_ports = ports

    bundle = SimpleNamespace(
        services=[
            DummyService({"http": 8080, "grpc": 50051}),
            DummyService({"ui": 8080, "metrics": 9090}),
        ]
    )
    ports = _collect_firewall_ports(bundle, server)
    assert ports == [22, 8080, 9090, 50051]
    assert _collect_firewall_port_rows(bundle, server) == [
        {"port_number": 22, "service": "Server", "port_name": "SSH"},
        {"port_number": 8080, "service": "DummyService", "port_name": "http"},
        {"port_number": 8080, "service": "DummyService", "port_name": "ui"},
        {"port_number": 9090, "service": "DummyService", "port_name": "metrics"},
        {"port_number": 50051, "service": "DummyService", "port_name": "grpc"},
    ]

    server.firewall_up(ports)
    server.firewall_update(ports)
    server.firewall_down()
    call_names = [name for name, _, _ in fake_exec.calls]
    assert "firewall_up" in call_names
    assert "firewall_update" in call_names
    assert "firewall_down" in call_names


def test_ubuntu_native_firewall_status_parsing_and_filtering():
    status = """Status: active
-N MLOX-FIREWALL
-A MLOX-FIREWALL -p tcp -m tcp --dport 22 -j ACCEPT
-A MLOX-FIREWALL -p tcp -m tcp --dport 8080 -j ACCEPT
-A MLOX-FIREWALL -p tcp -m tcp --dport 9090 -j DROP
-A MLOX-DOCKER-FIREWALL -p tcp -m conntrack --ctorigdstport 50051 -j ACCEPT
"""
    assert _parse_firewall_open_ports(status) == {22, 8080, 50051}
    assert _parse_firewall_open_ports("Status: inactive") == set()
    assert _parse_firewall_open_ports(None) is None

    rows = [
        {"port_number": 22, "service": "Server", "port_name": "SSH"},
        {"port_number": 8080, "service": "api", "port_name": "HTTP"},
    ]
    assert _filter_firewall_port_rows(rows, {22, 8080, 9999}) == [
        {"port_number": 22, "service": "Server", "port_name": "SSH"},
        {"port_number": 8080, "service": "api", "port_name": "HTTP"},
        {"port_number": 9999, "service": "Unknown", "port_name": "iptables rule"},
    ]
    assert _filter_firewall_port_rows(rows, None) == rows
    assert (
        _firewall_status_message("Status: inactive", set(), [])
        == "Firewall is not up. All ports are open."
    )
    assert (
        _firewall_status_message(None, None, rows)
        == "Could not read firewall status. Showing configured ports instead."
    )
    assert _firewall_status_message("Status: active", set(), []) == (
        "No open firewall ports found."
    )
    assert _firewall_status_message("Status: active", {22}, rows) is None
    assert _is_firewall_up("Status: active") is True
    assert _is_firewall_up("Status: inactive") is False
    assert _is_firewall_up(None) is False


def test_multipass_server_launches_before_ubuntu_setup(monkeypatch):
    from mlox.servers.ubuntu.multipass import MultipassUbuntuNativeServer

    server = MultipassUbuntuNativeServer(
        ip="mlox-unit-vm",
        port="22",
        root="root",
        root_pw="pass",
        service_config_id="ubuntu-multipass-native",
        vm_name="mlox-unit-vm",
        cpus="3",
        memory="6G",
        disk="30G",
    )
    calls = []
    monkeypatch.setattr(
        type(server), "is_multipass_available", property(lambda self: True)
    )
    monkeypatch.setattr(
        server,
        "launch_vm",
        lambda: (calls.append("launch"), setattr(server, "ip", "10.0.0.5")),
    )
    monkeypatch.setattr(
        UbuntuNativeServer,
        "setup",
        lambda self: calls.append(("ubuntu_setup", self.ip, self.state)),
    )

    assert server.test_connection() is True
    server.setup()

    assert calls == ["launch", ("ubuntu_setup", "10.0.0.5", "un-initialized")]
    assert server.vm_name == "mlox-unit-vm"
    assert server.cpus == "3"
    assert server.memory == "6G"
    assert server.disk == "30G"


def test_multipass_launch_waits_for_root_login(monkeypatch):
    from mlox.servers.ubuntu import multipass
    from mlox.servers.ubuntu.multipass import MultipassUbuntuNativeServer

    server = MultipassUbuntuNativeServer(
        ip="mlox-unit-vm",
        port="22",
        root="root",
        root_pw="pass",
        service_config_id="ubuntu-multipass-native",
        vm_name="mlox-unit-vm",
    )
    calls = []
    monkeypatch.setattr(
        type(server), "is_multipass_available", property(lambda self: True)
    )
    monkeypatch.setattr(multipass, "_HAS_MULTIPASS_SDK", False)
    monkeypatch.setattr(server, "_resolve_cloud_init_path", lambda: None)
    monkeypatch.setattr(
        server,
        "_run_multipass_cli",
        lambda *_args, **_kwargs: calls.append("launch"),
    )
    monkeypatch.setattr(server, "wait_for_ssh", lambda: "10.0.0.5")
    monkeypatch.setattr(
        server,
        "wait_for_root_login",
        lambda: calls.append("root-login"),
    )

    server.launch_vm()

    assert server.ip == "10.0.0.5"
    assert calls == ["launch", "root-login"]


def test_multipass_setup_cleans_up_vm_on_provisioning_failure(monkeypatch):
    from mlox.servers.ubuntu.multipass import MultipassUbuntuNativeServer

    server = MultipassUbuntuNativeServer(
        ip="mlox-unit-vm",
        port="22",
        root="root",
        root_pw="pass",
        service_config_id="ubuntu-multipass-native",
        vm_name="mlox-unit-vm",
    )
    calls = []
    monkeypatch.setattr(
        type(server), "is_multipass_available", property(lambda self: True)
    )
    monkeypatch.setattr(
        server,
        "launch_vm",
        lambda: (calls.append("launch"), setattr(server, "ip", "10.0.0.5")),
    )
    monkeypatch.setattr(server, "delete_vm", lambda: calls.append("delete"))
    monkeypatch.setattr(
        UbuntuNativeServer,
        "setup",
        lambda self: (_ for _ in ()).throw(RuntimeError("auth failed")),
    )

    try:
        server.setup()
    except RuntimeError:
        pass
    else:
        assert False, "Expected setup to raise"

    assert calls == ["launch", "delete"]
    assert server.ip == "mlox-unit-vm"
    assert server.state == "un-initialized"


def test_multipass_root_login_timeout_reports_command_output(monkeypatch):
    from mlox.servers.ubuntu.multipass import MultipassUbuntuNativeServer

    server = MultipassUbuntuNativeServer(
        ip="10.0.0.5",
        port="22",
        root="root",
        root_pw="pass",
        service_config_id="ubuntu-multipass-native",
        vm_name="mlox-unit-vm",
        launch_timeout="1",
    )

    @contextmanager
    def _conn():
        conn = SimpleNamespace()
        conn.run = lambda *_args, **_kwargs: SimpleNamespace(
            ok=False,
            stdout="status: error",
            stderr="",
            exited=2,
        )
        yield conn

    monkeypatch.setattr(
        server,
        "get_server_connection",
        lambda force_root=False: _conn(),
    )
    monkeypatch.setattr(
        "mlox.servers.ubuntu.multipass.time.time",
        iter([0, 0, 2]).__next__,
    )
    monkeypatch.setattr(
        "mlox.servers.ubuntu.multipass.time.sleep",
        lambda _seconds: None,
    )

    try:
        server.wait_for_root_login()
    except TimeoutError as exc:
        assert "status: error" in str(exc)
    else:
        assert False, "Expected root login wait to time out"


def test_multipass_start_stop_use_vm_sdk_methods(monkeypatch):
    from mlox.servers.ubuntu import multipass
    from mlox.servers.ubuntu.multipass import MultipassUbuntuNativeServer

    class _VM:
        def __init__(self):
            self.calls = []

        def start(self):
            self.calls.append("start")

        def stop(self):
            self.calls.append("stop")

    class _Client:
        def __init__(self):
            self.vm = vm

        def find(self, name):
            calls.append(("find", name))
            return self.vm

    vm = _VM()
    calls = []
    server = MultipassUbuntuNativeServer(
        ip="mlox-unit-vm",
        port="22",
        root="root",
        root_pw="pass",
        service_config_id="ubuntu-multipass-native",
        vm_name="mlox-unit-vm",
    )
    monkeypatch.setattr(multipass, "_HAS_MULTIPASS_SDK", True)
    monkeypatch.setattr(multipass, "MultipassClient", _Client)
    monkeypatch.setattr(server, "wait_for_ssh", lambda: "10.0.0.5")

    server.start_vm()
    server.stop_vm()

    assert calls == [("find", "mlox-unit-vm"), ("find", "mlox-unit-vm")]
    assert vm.calls == ["start", "stop"]
    assert server.ip == "10.0.0.5"
    assert server.state == "stopped"


def test_multipass_backend_status_includes_vm_metadata(monkeypatch):
    from mlox.servers.ubuntu.multipass import MultipassUbuntuDockerServer

    server = MultipassUbuntuDockerServer(
        ip="10.0.0.6",
        port="22",
        root="root",
        root_pw="pass",
        service_config_id="ubuntu-multipass-docker",
        vm_name="mlox-docker-vm",
        cpus="4",
        memory="8G",
        disk="40G",
    )
    monkeypatch.setattr(UbuntuDockerServer, "get_backend_status", lambda self: {"backend.is_running": True})
    monkeypatch.setattr(server, "multipass_info", lambda: {"state": "Running"})

    status = server.get_backend_status()

    assert status["backend.is_running"] is True
    assert status["multipass.vm_name"] == "mlox-docker-vm"
    assert status["multipass.ip"] == "10.0.0.6"
    assert status["multipass.cpus"] == "4"
    assert status["multipass.memory"] == "8G"
    assert status["multipass.disk"] == "40G"
    assert status["multipass.info"] == {"state": "Running"}
