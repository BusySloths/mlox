import uuid
import time
import pytest
import socket
import logging
from pathlib import Path
from multipass import MultipassClient, MultipassVM  # type: ignore

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure

# Mark this module as an integration test
pytestmark = pytest.mark.integration


def wait_for_ssh(
    vm: MultipassVM, vm_name: str, timeout: int = 120, interval: float = 2.0
) -> str:
    """Wait until the VM has an IPv4 and port 22 is reachable. Returns the ip when ready."""
    deadline = time.time() + timeout
    last_exc = None
    while time.time() < deadline:
        try:
            info = vm.info()
            # info JSON structure varies; try common shapes
            data = (
                info.get("info", {}).get(vm_name, info)
                if isinstance(info, dict)
                else {}
            )
            # look for ipv4
            ip = None
            if isinstance(data, dict):
                ipv4 = data.get("ipv4")
                if isinstance(ipv4, list) and ipv4:
                    ip = ipv4[0]
                elif isinstance(ipv4, str):
                    ip = ipv4
            if ip:
                # quick TCP connect check for port 22
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                try:
                    if s.connect_ex((ip, 22)) == 0:
                        s.close()
                        return ip
                finally:
                    s.close()
        except Exception as e:
            last_exc = e
        time.sleep(interval)
    raise TimeoutError(
        f"VM {vm_name} SSH not reachable after {timeout}s. Last error: {last_exc!r}"
    )


@pytest.fixture(scope="module")
def multipass_instance():
    """Launch a temporary Multipass VM and clean it up afterwards.
    Requires the unofficial multipass-sdk to be installed on the host.
    """
    client = MultipassClient()
    name = f"mlox-test-{uuid.uuid4().hex[:8]}"
    cloud_init_path = (
        Path(__file__).resolve().parents[2] / "mlox/assets/cloud-init.yaml"
    )

    try:
        # Launch the instance with the same settings as the project's helper script
        logging.info(f"Launching Multipass VM {name} with cloud-init {cloud_init_path}")
        vm = client.launch(
            vm_name=name, cpu=2, disk="10G", mem="4G", cloud_init=cloud_init_path
        )
        try:
            ip = wait_for_ssh(vm, name, timeout=180, interval=3.0)
        except TimeoutError:
            client.delete(name, purge=True)
            pytest.fail("Multipass VM did not become SSH-ready in time")
        # now proceed and yield ip
        info = vm.info()
        ip = None
        if "info" in info and name in info["info"]:
            info = info["info"][name]

        ip = info["ipv4"][0] if isinstance(info.get("ipv4"), list) else info["ipv4"]
        print(info, name, ip)

        if not ip:
            client.delete(name, purge=True)
            pytest.fail("Could not determine IP address of the Multipass VM")

        logging.info(f"Multipass VM {name} is running at IP {ip}")
        yield {"client": client, "vm": vm, "name": name, "ip": ip}

    finally:
        try:
            client.delete(name, purge=True)
        except Exception:
            pass


@pytest.fixture(scope="module")
def ubuntu_docker_server(multipass_instance):
    """Provision and fully set up an Ubuntu server with a Docker backend."""
    infra = Infrastructure()
    config = load_config(get_stacks_path(), "/ubuntu", "mlox-server.ubuntu.docker.yaml")
    params = {
        "${MLOX_IP}": multipass_instance["ip"],
        "${MLOX_PORT}": "22",
        "${MLOX_ROOT}": "root",
        "${MLOX_ROOT_PW}": "pass",
    }
    bundle = infra.add_server(config, params)
    if not bundle:
        pytest.skip("Failed to add server to infrastructure")
    server = bundle.server
    server.setup()
    yield server
    try:
        server.teardown()
    except Exception:
        pass
    infra.remove_bundle(bundle)


def test_backend_is_running(ubuntu_docker_server):
    """Ensure the Docker backend is installed and running on the server."""
    assert "docker" in ubuntu_docker_server.backend
    status = ubuntu_docker_server.get_backend_status()
    assert status.get("docker.is_running")
