"""End-to-end firewall tests on dedicated, disposable Ubuntu VMs.

Run only on a machine with Multipass, network access, and Docker image access::

    uv run pytest tests/integration/test_ubuntu_firewall.py --run-integration -v

The module provisions separate native and Docker guests. It creates client
network namespaces *inside* each guest, changes that guest's firewall, and
reboots it. It must never target an existing or user-supplied server.
"""

from __future__ import annotations

import json
import shlex
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from mlox.firewall import FirewallPolicy
from mlox.servers.ubuntu.docker import UbuntuDockerServer
from mlox.servers.ubuntu.native import UbuntuNativeServer
from tests.integration.conftest import (
    MultipassClient,
    _HAS_MULTIPASS,
    wait_for_server_login,
    wait_for_ssh,
)


pytestmark = pytest.mark.integration

V4_HOST, V4_TRUSTED, V4_OTHER, V4_OUTSIDE = "198.18.17.1", "198.18.17.2", "198.18.17.3", "198.18.17.4"
V6_HOST, V6_TRUSTED, V6_OTHER, V6_OUTSIDE = "fd52:fa:17::1", "fd52:fa:17::2", "fd52:fa:17::3", "fd52:fa:17::4"
IMAGE = "python:3.12-alpine"


def _sudo(conn, args: list[str], *, timeout: int = 30) -> str:
    """Run one checked command on the disposable guest, not the test host."""
    result = conn.sudo(shlex.join(args), hide=True, warn=False, pty=False, timeout=timeout)
    return result.stdout.strip()


def _run(conn, args: list[str], *, timeout: int = 30) -> str:
    result = conn.run(shlex.join(args), hide=True, warn=False, pty=False, timeout=timeout)
    return result.stdout.strip()


@dataclass
class FirewallGuest:
    server: UbuntuNativeServer
    vm: object
    vm_name: str
    docker: bool

    def reboot(self) -> None:
        # MLOX hardens SSH during setup; Multipass's own SSH credentials may no
        # longer work for its restart command. Schedule a guest reboot using
        # the MLOX credentials instead, and confirm a new kernel boot ID.
        with self.server.get_server_connection() as conn:
            boot_id = _run(conn, ["cat", "/proc/sys/kernel/random/boot_id"])
            _sudo(conn, ["systemd-run", "--on-active=3s", "/usr/bin/systemctl", "reboot"])

        deadline = time.monotonic() + 180
        last_error = None
        while time.monotonic() < deadline:
            try:
                self.server.ip = wait_for_ssh(self.vm, self.vm_name, timeout=10, interval=1)
                with self.server.get_server_connection() as conn:
                    if _run(conn, ["cat", "/proc/sys/kernel/random/boot_id"]) != boot_id:
                        return
            except Exception as exc:
                last_error = exc
            time.sleep(3)
        raise TimeoutError(f"VM {self.vm_name} did not complete a reboot: {last_error!r}")


@pytest.fixture(scope="module", params=["native", "docker"])
def firewall_guest(request):
    """Always create a fresh guest; never accept a production address as input."""
    if not _HAS_MULTIPASS or not shutil.which("multipass"):
        pytest.skip("Firewall integration tests require Multipass and its Python SDK")

    name = f"mlox-firewall-{request.param}-{uuid.uuid4().hex[:8]}"
    client = MultipassClient()
    vm = None
    server = None
    try:
        cloud_init = Path(__file__).resolve().parents[2] / "mlox/assets/cloud-init.yaml"
        vm = client.launch(vm_name=name, cpu=2, disk="20G", mem="4G", cloud_init=str(cloud_init))
        ip = wait_for_ssh(vm, name, timeout=180, interval=3)
        cls = UbuntuDockerServer if request.param == "docker" else UbuntuNativeServer
        server = cls(ip=ip, port="22", root="root", root_pw="pass", service_config_id="firewall-integration")
        wait_for_server_login(server, force_root=True)
        server.setup()
        assert server.state == "running"
        yield FirewallGuest(server, vm, name, request.param == "docker")
    finally:
        # Purge only the VM named by this fixture, never all deleted VMs.
        if vm is not None:
            subprocess.run(["multipass", "delete", "--purge", name], check=True, timeout=180)


@dataclass
class NetworkProbe:
    guest: FirewallGuest
    namespace: str
    host_link: str
    units: list[str]
    containers: list[str]
    networks: list[str]

    def start_http(self, conn, family: int) -> int:
        bind = "0.0.0.0" if family == 4 else "::"
        script = (
            "import socket,sys; "
            "s=socket.socket(socket.AF_INET if sys.argv[1]=='4' else socket.AF_INET6); "
            "s.bind((sys.argv[2],0)); print(s.getsockname()[1]); s.close()"
        )
        port = int(_run(conn, ["python3", "-c", script, str(family), bind]))
        unit = f"mlox-fw-http-{uuid.uuid4().hex[:10]}"
        self.units.append(unit)
        _sudo(conn, ["systemd-run", "--unit", unit, "--collect", "/usr/bin/python3", "-m", "http.server", str(port), "--bind", bind])
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = conn.sudo(shlex.join(["systemctl", "is-active", "--quiet", unit]), hide=True, warn=True, pty=False)
            source, target = (V4_OTHER, V4_HOST) if family == 4 else (V6_OTHER, V6_HOST)
            if result.ok and self.probe(conn, source, target, port) == "open":
                return port
            time.sleep(0.25)
        pytest.fail(f"HTTP probe unit {unit} did not start")

    def probe(self, conn, source: str, destination: str, port: int) -> str:
        script = """import socket, sys
source, dest, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
s = socket.socket(socket.AF_INET6 if ':' in source else socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.bind((source, 0))
    s.connect((dest, port))
    s.sendall(b'GET / HTTP/1.0\\r\\nHost: test\\r\\n\\r\\n')
    data = s.recv(128)
    print('open' if data.startswith(b'HTTP/') else 'bad-response')
except TimeoutError:
    print('timeout')
except OSError as exc:
    print('error:' + str(exc.errno))
finally:
    s.close()
"""
        return _sudo(conn, ["ip", "netns", "exec", self.namespace, "python3", "-c", script, source, destination, str(port)])

    def start_udp_echo(self, conn) -> int:
        choose = "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(('0.0.0.0',0)); print(s.getsockname()[1])"
        port = int(_run(conn, ["python3", "-c", choose]))
        unit = f"mlox-fw-udp-{uuid.uuid4().hex[:10]}"
        self.units.append(unit)
        script = """import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('0.0.0.0', int(sys.argv[1])))
while True:
    data, peer = s.recvfrom(1024)
    s.sendto(data, peer)
"""
        _sudo(conn, ["systemd-run", "--unit", unit, "--collect", "/usr/bin/python3", "-c", script, str(port)])
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.probe_udp(conn, V4_OTHER, V4_HOST, port) == "open":
                return port
            time.sleep(0.25)
        pytest.fail(f"UDP echo unit {unit} did not become reachable")

    def probe_udp(self, conn, source: str, destination: str, port: int) -> str:
        script = """import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
try:
    s.bind((sys.argv[1], 0))
    s.sendto(b'probe', (sys.argv[2], int(sys.argv[3])))
    print('open' if s.recvfrom(1024)[0] == b'probe' else 'bad-response')
except TimeoutError:
    print('timeout')
except OSError as exc:
    print('error:' + str(exc.errno))
finally:
    s.close()
"""
        return _sudo(conn, ["ip", "netns", "exec", self.namespace, "python3", "-c", script, source, destination, str(port)])

    def start_container(self, conn, name: str, *args: str) -> None:
        self.containers.append(name)
        _sudo(conn, ["docker", "run", "-d", "--name", name, *args], timeout=120)

    def start_network(self, conn, name: str) -> None:
        self.networks.append(name)
        _sudo(conn, ["docker", "network", "create", name])

    def wait_open(self, conn, source: str, destination: str, port: int) -> None:
        deadline = time.monotonic() + 30
        last = ""
        while time.monotonic() < deadline:
            last = self.probe(conn, source, destination, port)
            if last == "open":
                return
            time.sleep(0.25)
        pytest.fail(f"Probe to {destination}:{port} never became reachable: {last}")


@pytest.fixture
def network_probe(firewall_guest):
    """Two independent IPv4/IPv6 client addresses, connected by a guest veth."""
    server = firewall_guest.server
    token = uuid.uuid4().hex[:7]
    namespace, host_link, peer_link = f"mlox-fw-{token}", f"fwh{token}", f"fwp{token}"
    probe = NetworkProbe(firewall_guest, namespace, host_link, [], [], [])
    server.firewall_down()
    try:
        with server.get_server_connection() as conn:
            _sudo(conn, ["ip", "netns", "add", namespace])
            _sudo(conn, ["ip", "link", "add", host_link, "type", "veth", "peer", "name", peer_link])
            _sudo(conn, ["ip", "link", "set", peer_link, "netns", namespace])
            _sudo(conn, ["ip", "addr", "add", f"{V4_HOST}/29", "dev", host_link])
            _sudo(conn, ["ip", "-6", "addr", "add", f"{V6_HOST}/64", "dev", host_link, "nodad"])
            _sudo(conn, ["ip", "link", "set", host_link, "up"])
            _sudo(conn, ["ip", "-n", namespace, "link", "set", "lo", "up"])
            for source in (V4_TRUSTED, V4_OTHER, V4_OUTSIDE):
                _sudo(conn, ["ip", "-n", namespace, "addr", "add", f"{source}/29", "dev", peer_link])
            for source in (V6_TRUSTED, V6_OTHER, V6_OUTSIDE):
                _sudo(conn, ["ip", "-n", namespace, "-6", "addr", "add", f"{source}/64", "dev", peer_link, "nodad"])
            _sudo(conn, ["ip", "-n", namespace, "link", "set", peer_link, "up"])
        yield probe
    finally:
        try:
            server.firewall_down()
        finally:
            with server.get_server_connection() as conn:
                for name in reversed(probe.containers):
                    conn.sudo(shlex.join(["docker", "rm", "-f", name]), hide=True, warn=True, pty=False)
                for name in reversed(probe.networks):
                    conn.sudo(shlex.join(["docker", "network", "rm", name]), hide=True, warn=True, pty=False)
                for unit in probe.units:
                    conn.sudo(shlex.join(["systemctl", "stop", unit]), hide=True, warn=True, pty=False)
                conn.sudo(shlex.join(["ip", "netns", "del", namespace]), hide=True, warn=True, pty=False)
                conn.sudo(shlex.join(["ip", "link", "del", host_link]), hide=True, warn=True, pty=False)


def _policy(guest: FirewallGuest, *, ports=(), sources=()) -> FirewallPolicy:
    return FirewallPolicy((int(guest.server.port), *ports), tuple(sources))


@pytest.mark.parametrize(
    "family,host,trusted,other,prefix",
    [(4, V4_HOST, V4_TRUSTED, V4_OTHER, 32), (6, V6_HOST, V6_TRUSTED, V6_OTHER, 128)],
)
def test_host_public_trusted_and_blocked_traffic(network_probe, family, host, trusted, other, prefix):
    guest = network_probe.guest
    server = guest.server
    with server.get_server_connection() as conn:
        public_port = network_probe.start_http(conn, family)
        private_port = network_probe.start_http(conn, family)
        assert network_probe.probe(conn, other, host, public_port) == "open"
        assert network_probe.probe(conn, other, host, private_port) == "open"
        policy = _policy(guest, ports=(public_port,), sources=(f"{trusted}/{prefix}",))
        server.firewall_apply_policy(policy)
        status = server.firewall_status()
        assert status.active is True and not status.error
        assert public_port in status.public_ports
        assert trusted in status.trusted_sources
        assert network_probe.probe(conn, other, host, public_port) == "open"
        assert network_probe.probe(conn, trusted, host, private_port) == "open"
        assert network_probe.probe(conn, other, host, private_port) == "timeout"
        server.firewall_apply_policy(_policy(guest, ports=(public_port,)))
        assert network_probe.probe(conn, trusted, host, private_port) == "timeout"
    # The management port must remain reachable through a fresh SSH session.
    with server.get_server_connection() as conn:
        assert _run(conn, ["true"]) == ""


def test_existing_connection_survives_policy_but_new_connection_is_blocked(network_probe):
    guest = network_probe.guest
    with guest.server.get_server_connection() as conn:
        port = network_probe.start_http(conn, 4)
        with socket.create_connection((guest.server.ip, port), timeout=5) as existing:
            guest.server.firewall_apply_policy(_policy(guest))
            existing.settimeout(5)
            existing.sendall(b"GET / HTTP/1.0\r\nHost: test\r\n\r\n")
            assert existing.recv(128).startswith(b"HTTP/")
        with pytest.raises(TimeoutError):
            socket.create_connection((guest.server.ip, port), timeout=2)


@pytest.mark.parametrize(
    "family,host,trusted,other,outside,network",
    [(4, V4_HOST, V4_TRUSTED, V4_OTHER, V4_OUTSIDE, "198.18.17.2/31"),
     (6, V6_HOST, V6_TRUSTED, V6_OTHER, V6_OUTSIDE, "fd52:fa:17::2/127")],
)
def test_trusted_cidr_covers_only_its_members(network_probe, family, host, trusted, other, outside, network):
    guest = network_probe.guest
    with guest.server.get_server_connection() as conn:
        port = network_probe.start_http(conn, family)
        assert network_probe.probe(conn, outside, host, port) == "open"
        guest.server.firewall_apply_policy(_policy(guest, sources=(network,)))
        assert network_probe.probe(conn, trusted, host, port) == "open"
        assert network_probe.probe(conn, other, host, port) == "open"
        assert network_probe.probe(conn, outside, host, port) == "timeout"


def test_policy_rejects_missing_ssh_port_before_changing_rules(network_probe):
    server = network_probe.guest.server
    assert server.firewall_status().active is False
    with pytest.raises(ValueError, match="SSH port"):
        server.firewall_apply_policy(FirewallPolicy((80, 443)))
    assert server.firewall_status().active is False
    with server.get_server_connection() as conn:
        assert _run(conn, ["true"]) == ""


def test_udp_is_restricted_but_ipv6_control_traffic_remains_available(network_probe):
    guest = network_probe.guest
    with guest.server.get_server_connection() as conn:
        port = network_probe.start_udp_echo(conn)
        assert network_probe.probe_udp(conn, V4_OTHER, V4_HOST, port) == "open"
        _sudo(conn, ["ip", "netns", "exec", network_probe.namespace, "ping", "-6", "-c", "1", "-W", "2", V6_HOST])
        guest.server.firewall_apply_policy(_policy(guest, sources=(f"{V4_TRUSTED}/32",)))
        assert network_probe.probe_udp(conn, V4_OTHER, V4_HOST, port) == "timeout"
        assert network_probe.probe_udp(conn, V4_TRUSTED, V4_HOST, port) == "open"
        _sudo(conn, ["ip", "netns", "exec", network_probe.namespace, "ping", "-6", "-c", "1", "-W", "2", V6_HOST])


def test_apply_is_idempotent_and_preserves_unrelated_rules(network_probe):
    guest = network_probe.guest
    with guest.server.get_server_connection() as conn:
        for tool in ("iptables", "ip6tables"):
            _sudo(conn, [tool, "-N", "MLOX-TEST-UNRELATED"])
        try:
            policy = _policy(guest, sources=(f"{V4_TRUSTED}/32", f"{V6_TRUSTED}/128"))
            guest.server.firewall_apply_policy(policy)
            guest.server.firewall_apply_policy(policy)
            for tool in ("iptables", "ip6tables"):
                lines = _sudo(conn, [tool, "-S", "INPUT"]).splitlines()
                assert lines.count("-A INPUT -j MLOX-POLICY-IN") == 1
                assert "-N MLOX-TEST-UNRELATED" in _sudo(conn, [tool, "-S", "MLOX-TEST-UNRELATED"])
        finally:
            for tool in ("iptables", "ip6tables"):
                _sudo(conn, [tool, "-X", "MLOX-TEST-UNRELATED"])


def test_apply_replaces_legacy_managed_hooks(network_probe):
    guest = network_probe.guest
    with guest.server.get_server_connection() as conn:
        _sudo(conn, ["iptables", "-N", "MLOX-FIREWALL"])
        _sudo(conn, ["iptables", "-A", "MLOX-FIREWALL", "-p", "tcp", "--dport", str(guest.server.port), "-j", "ACCEPT"])
        _sudo(conn, ["iptables", "-A", "MLOX-FIREWALL", "-j", "DROP"])
        _sudo(conn, ["iptables", "-I", "INPUT", "1", "-p", "tcp", "-j", "MLOX-FIREWALL"])
        assert guest.server.firewall_status().previous_policy
        guest.server.firewall_apply_policy(_policy(guest))
        hooks = _sudo(conn, ["iptables", "-S", "INPUT"]).splitlines()
        assert "-A INPUT -p tcp -j MLOX-FIREWALL" not in hooks
        assert "-A INPUT -j MLOX-POLICY-IN" in hooks
        assert not guest.server.firewall_status().previous_policy


def test_native_policy_does_not_require_docker_chains(firewall_guest):
    if firewall_guest.docker:
        pytest.skip("This test checks a native guest without Docker")
    server = firewall_guest.server
    server.firewall_down()
    try:
        with server.get_server_connection() as conn:
            for tool in ("iptables", "ip6tables"):
                check = conn.sudo(shlex.join([tool, "-S", "DOCKER-USER"]), hide=True, warn=True, pty=False)
                assert not check.ok, f"Unexpected Docker chain in native guest: {tool}"
        server.firewall_apply_policy(_policy(firewall_guest))
        status = server.firewall_status()
        assert status.active is True and not status.error
        with server.get_server_connection() as conn:
            for tool in ("iptables", "ip6tables"):
                _sudo(conn, [tool, "-C", "INPUT", "-j", "MLOX-POLICY-IN"])
    finally:
        server.firewall_down()


def test_docker_published_ports_and_proxy_to_host_gateway(network_probe):
    guest = network_probe.guest
    if not guest.docker:
        pytest.skip("Docker forwarding is covered only by the Docker guest")
    token = uuid.uuid4().hex[:10]
    backend_net, proxy_net = f"mlox-fw-back-{token}", f"mlox-fw-proxy-{token}"
    private, public, proxy = f"mlox-fw-private-{token}", f"mlox-fw-public-{token}", f"mlox-fw-proxy-{token}"
    with guest.server.get_server_connection() as conn:
        _sudo(conn, ["docker", "pull", IMAGE], timeout=240)
        network_probe.start_network(conn, backend_net)
        network_probe.start_network(conn, proxy_net)
        for name in (private, public):
            network_probe.start_container(conn, name, "--network", backend_net, "-p", "0.0.0.0::8080", IMAGE,
                                          "python", "-m", "http.server", "8080", "--bind", "0.0.0.0")
        network_probe.start_container(conn, proxy, "--network", proxy_net, "--add-host", "host.docker.internal:host-gateway",
                                      IMAGE, "python", "-c", "import time; time.sleep(3600)")
        def port(name):
            raw = _sudo(conn, ["docker", "inspect", "--format", '{{json (index .NetworkSettings.Ports "8080/tcp")}}', name])
            return int(json.loads(raw)[0]["HostPort"])
        private_port, public_port = port(private), port(public)
        network_probe.wait_open(conn, V4_OTHER, V4_HOST, private_port)
        network_probe.wait_open(conn, V4_OTHER, V4_HOST, public_port)
        guest.server.firewall_apply_policy(_policy(guest, ports=(public_port,), sources=(f"{V4_TRUSTED}/32",)))
        assert network_probe.probe(conn, V4_OTHER, V4_HOST, public_port) == "open"
        assert network_probe.probe(conn, V4_OTHER, V4_HOST, private_port) == "timeout"
        assert network_probe.probe(conn, V4_TRUSTED, V4_HOST, private_port) == "open"
        script = "import sys,urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=5).status)"
        # This follows Traefik's container -> host gateway -> published port path.
        assert _sudo(conn, ["docker", "exec", proxy, "python", "-c", script,
                            f"http://host.docker.internal:{private_port}/"]) == "200"


def test_docker_ipv6_published_port_respects_trusted_sources(network_probe):
    guest = network_probe.guest
    if not guest.docker:
        pytest.skip("Docker port publishing is covered only by the Docker guest")
    name = f"mlox-fw-v6-{uuid.uuid4().hex[:10]}"
    with guest.server.get_server_connection() as conn:
        _sudo(conn, ["docker", "pull", IMAGE], timeout=240)
        network_probe.start_container(conn, name, "-p", "[::]::8080", IMAGE,
                                      "python", "-m", "http.server", "8080", "--bind", "0.0.0.0")
        raw = _sudo(conn, ["docker", "inspect", "--format", '{{json (index .NetworkSettings.Ports "8080/tcp")}}', name])
        bindings = json.loads(raw)
        port = int(next(binding["HostPort"] for binding in bindings if binding["HostIp"] == "::"))
        network_probe.wait_open(conn, V6_OTHER, V6_HOST, port)
        guest.server.firewall_apply_policy(_policy(guest, sources=(f"{V6_TRUSTED}/128",)))
        assert network_probe.probe(conn, V6_OTHER, V6_HOST, port) == "timeout"
        assert network_probe.probe(conn, V6_TRUSTED, V6_HOST, port) == "open"
        guest.server.firewall_apply_policy(_policy(guest, ports=(port,)))
        assert network_probe.probe(conn, V6_OTHER, V6_HOST, port) == "open"


def test_persistence_rejects_mismatched_draft_and_survives_reboot(firewall_guest):
    server = firewall_guest.server
    server.firewall_down()
    try:
        applied = _policy(firewall_guest, sources=(f"{V4_TRUSTED}/32",))
        server.firewall_apply_policy(applied)
        with pytest.raises(RuntimeError, match="match the draft"):
            server.firewall_persist_policy(_policy(firewall_guest))
        assert server.firewall_status().persistence != "enabled"
        server.firewall_persist_policy(applied)
        assert server.firewall_status().persistence == "enabled"
        firewall_guest.reboot()
        deadline = time.monotonic() + 60
        while True:
            status = server.firewall_status()
            if status.active and status.persistence == "enabled":
                break
            if time.monotonic() >= deadline:
                pytest.fail(f"Firewall was not restored after reboot: {status}")
            time.sleep(2)
        assert not status.error
        assert V4_TRUSTED in status.trusted_sources
        with server.get_server_connection() as conn:
            assert _sudo(conn, ["systemctl", "is-active", "mlox-firewall-policy.service"]) == "active"
            for tool in ("iptables", "ip6tables"):
                _sudo(conn, [tool, "-C", "INPUT", "-j", "MLOX-POLICY-IN"])
                if firewall_guest.docker:
                    _sudo(conn, [tool, "-C", "DOCKER-USER", "-j", "MLOX-POLICY-DOCKER"])
        server.firewall_down()
        assert server.firewall_status().persistence == "disabled"
        firewall_guest.reboot()
        assert server.firewall_status().active is False
    finally:
        server.firewall_down()


def test_temporary_policy_does_not_survive_reboot(firewall_guest):
    server = firewall_guest.server
    server.firewall_down()
    try:
        server.firewall_apply_policy(_policy(firewall_guest))
        assert server.firewall_status().active is True
        assert server.firewall_status().persistence != "enabled"
        firewall_guest.reboot()
        assert server.firewall_status().active is False
    finally:
        server.firewall_down()
