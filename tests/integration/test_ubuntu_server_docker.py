import uuid
from pathlib import Path

import pytest

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure

# Mark this module as an integration test
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def multipass_instance():
    """Launch a temporary Multipass VM and clean it up afterwards.

    Requires the unofficial multipass-sdk to be installed on the host.
    """
    try:
        from multipass import Client
    except Exception:
        pytest.skip("multipass-sdk not available")

    client = Client()
    name = f"mlox-test-{uuid.uuid4().hex[:8]}"
    cloud_init_path = Path(__file__).resolve().parents[2] / "cloud-init.yaml"
    with open(cloud_init_path, "r", encoding="utf-8") as f:
        cloud_init = f.read()

    try:
        # Launch the instance with the same settings as the project's helper script
        client.launch(
            name=name,
            cpus=2,
            disk="10G",
            mem="4G",
            cloud_init=cloud_init,
        )
        info = client.info(name)
        ip = info["ipv4"][0] if isinstance(info.get("ipv4"), list) else info["ipv4"]
        yield {"client": client, "name": name, "ip": ip}
    finally:
        try:
            client.delete(name, purge=True)
        except Exception:
            pass


@pytest.fixture(scope="module")
def ubuntu_docker_server(multipass_instance):
    """Provision and fully set up an Ubuntu server with a Docker backend."""
    infra = Infrastructure()
    config = load_config(
        get_stacks_path(), "/ubuntu", "mlox-server.ubuntu.docker.yaml"
    )
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
