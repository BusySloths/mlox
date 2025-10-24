import uuid
import time
import socket
import logging
import pytest

from pathlib import Path
from typing import Callable, Dict, Optional

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure

logger = logging.getLogger(__name__)
try:
    from multipass import MultipassClient, MultipassVM  # type: ignore

    _HAS_MULTIPASS = True
except Exception:  # pragma: no cover - optional dependency
    MultipassClient = None  # type: ignore
    MultipassVM = None  # type: ignore
    _HAS_MULTIPASS = False
    logger.warning("multipass package not available; do not run integration tests.")


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


def wait_for_service_ready(
    service,
    bundle,
    check_fn: Optional[Callable[[], Dict[str, str]]] = None,
    retries: int = 40,
    interval: int = 60,
    no_checks: bool = False,
) -> Dict[str, str]:
    """Poll a service until it reports ``status == 'running'``.

    Parameters
    ----------
    service: AbstractService
        Service instance to check.
    bundle: Bundle
        Bundle containing the server the service is running on.
    check_fn: Callable, optional
        Optional custom check function returning a status dict. If not
        provided, ``service.check`` is invoked using a server connection.
    retries: int
        Number of times to poll before giving up.
    interval: int
        Sleep interval in seconds between polls.
    no_checks: bool
        If True, skip all checks and wait 'retries x interval' seconds.

    Returns
    -------
    Dict[str, str]
        The last status dictionary returned by the check function.
    """

    status: Dict[str, str] = {"status": "unknown"}
    for i in range(retries):
        try:
            if no_checks:
                status = {"status": "unknown"}
            else:
                if check_fn:
                    status = check_fn()
                else:
                    with bundle.server.get_server_connection() as conn:
                        status = service.check(conn)
                if status.get("status") == "running":
                    return status
            logging.warning(
                f"Retry {i + 1}/{retries} in {interval}s. Service state {getattr(service, 'state', '?')} not yet running: {status}"
            )
        except Exception as e:
            status = {"status": "unknown", "error": str(e)}
            logging.warning(
                f"Retry {i + 1}/{retries} in {interval}s. Exception during status check: {e}"
            )
        time.sleep(interval)
    return status


@pytest.fixture(scope="package")
def multipass_instance():
    if not _HAS_MULTIPASS:
        pytest.skip(
            "multipass package not available; skip integration tests that require Multipass"
        )

    client = MultipassClient()
    name = f"mlox-test-{uuid.uuid4().hex[:8]}"
    cloud_init_path = (
        Path(__file__).resolve().parents[2] / "mlox/assets/cloud-init.yaml"
    )
    logging.info(f"Launching Multipass VM {name} with cloud-init {cloud_init_path}")
    vm = client.launch(
        vm_name=name, cpu=4, disk="40G", mem="12G", cloud_init=cloud_init_path
    )
    # wait_for_ssh(...) same implementation as in your test file
    ip = wait_for_ssh(vm, name, timeout=180, interval=3.0)
    vm.info()
    logging.info(f"Multipass VM {name} is running at IP {ip}")
    yield {"client": client, "vm": vm, "name": name, "ip": ip}
    logging.info(f"Cleaning up Multipass VM {name}...")
    try:
        vm.delete()
        client.purge()
        # client.delete(name, purge=True)
        logging.info(f"Successfully cleaned up Multipass VM {name}.")
    except Exception as e:
        logging.warning(f"Could not clean up Multipass VM {name}: {e}")


@pytest.fixture(scope="package")
def ubuntu_docker_server(multipass_instance):
    infra = Infrastructure()
    config = load_config(
        get_stacks_path(prefix="mlox-server"),
        "/ubuntu",
        "mlox-server.ubuntu.docker.yaml",
    )
    params = {
        "${MLOX_IP}": multipass_instance["ip"],
        "${MLOX_PORT}": "22",
        "${MLOX_ROOT}": "root",
        "${MLOX_ROOT_PW}": "pass",
    }
    bundle = infra.add_server(config, params)
    if not bundle:
        pytest.fail("Failed to add server to infrastructure")
    server = bundle.server
    server.setup()

    def _list_docker_volumes() -> set[str]:
        try:
            with server.get_server_connection(force_root=True) as conn:
                res = conn.run("docker volume ls -q", hide=True, warn=True, pty=False)
                output = (res.stdout or "").strip().splitlines()
                return {line.strip() for line in output if line.strip()}
        except Exception as exc:  # pragma: no cover - best effort cleanup safeguard
            logging.error(f"Unable to list docker volumes: {exc}")
            return set()

    baseline_volumes = _list_docker_volumes()
    yield server
    logging.info(
        f"Tearing down ubuntu_docker_server on VM {multipass_instance['name']}..."
    )
    remaining_volumes = _list_docker_volumes()
    new_volumes = sorted(remaining_volumes - baseline_volumes)
    missing_volumes = sorted(baseline_volumes - remaining_volumes)
    if new_volumes:
        logging.error("Docker volumes left behind after teardown: %s", new_volumes)
    if missing_volumes:
        logging.warning(
            "Baseline docker volumes removed during teardown: %s", missing_volumes
        )
    try:
        server.teardown()
        logging.info("Successfully tore down ubuntu_docker_server.")
    except Exception as e:
        logging.warning(f"Could not tear down ubuntu_docker_server: {e}")
    infra.remove_bundle(bundle)


# @pytest.fixture(scope="package")
# def ubuntu_native_server(multipass_instance):
#     infra = Infrastructure()
#     config = load_config(get_stacks_path(), "/ubuntu", "mlox-server.ubuntu.native.yaml")
#     params = {
#         "${MLOX_IP}": multipass_instance["ip"],
#         "${MLOX_PORT}": "22",
#         "${MLOX_ROOT}": "root",
#         "${MLOX_ROOT_PW}": "pass",
#     }
#     bundle = infra.add_server(config, params)
#     if not bundle:
#         pytest.fail("Failed to add server to infrastructure")
#     server = bundle.server
#     server.setup()
#     yield server
#     logging.info(
#         f"Tearing down ubuntu_native_server on VM {multipass_instance['name']}..."
#     )
#     try:
#         server.teardown()
#         logging.info("Successfully tore down ubuntu_native_server.")
#     except Exception as e:
#         logging.warning(f"Could not tear down ubuntu_native_server: {e}")
#     infra.remove_bundle(bundle)
