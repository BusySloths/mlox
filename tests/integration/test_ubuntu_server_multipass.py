from tests.integration.helpers import add_server
import logging
import shutil
import uuid

import pytest

from mlox.config import get_stacks_path, load_config
from mlox.infra import Infrastructure

pytestmark = pytest.mark.integration


def _multipass_available() -> bool:
    try:
        import multipass  # noqa: F401

        return True
    except Exception:
        return shutil.which("multipass") is not None


@pytest.mark.skipif(not _multipass_available(), reason="Multipass is not available")
@pytest.mark.parametrize(
    "template,expected_backend",
    [
        ("mlox-server.ubuntu.multipass.native.yaml", "native"),
        ("mlox-server.ubuntu.multipass.docker.yaml", "docker"),
        ("mlox-server.ubuntu.multipass.k3s.yaml", "kubernetes"),
    ],
)
def test_multipass_ubuntu_server_lifecycle(template, expected_backend):
    infra = Infrastructure()
    config = load_config(get_stacks_path(prefix="mlox-server"), "/ubuntu", template)
    name = f"mlox-it-{uuid.uuid4().hex[:8]}"
    params = {
        "${MULTIPASS_VM_NAME}": name,
        "${MULTIPASS_CPUS}": "2",
        "${MULTIPASS_MEMORY}": "4G",
        "${MULTIPASS_DISK}": "20G",
        "${MULTIPASS_IMAGE}": "24.04",
        "${MULTIPASS_CLOUD_INIT}": "",
        "${MULTIPASS_LAUNCH_TIMEOUT}": "600",
        "${K3S_CONTROLLER_URL}": "",
        "${K3S_CONTROLLER_TOKEN}": "",
        "${K3S_CONTROLLER_UUID}": "",
    }
    bundle = add_server(infra, config, params)
    assert bundle is not None
    server = bundle.server
    try:
        assert expected_backend in server.backend
        server.setup()
        assert server.state == "running"
        assert server.ip != name
        with server.get_server_connection() as conn:
            assert conn.run("true", hide=True).ok
    finally:
        logging.info("Tearing down Multipass VM %s", name)
        server.teardown()
        infra.remove_bundle(bundle)
