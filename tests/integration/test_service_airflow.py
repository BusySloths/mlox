from tests.integration.helpers import add_service, remove_service
import shlex
import time
import pytest
import logging

from mlox.config import load_config, get_stacks_path
from mlox.execution.base import TaskGroup
from mlox.infra import Infrastructure, Bundle
from mlox.service import ServiceCapability

from tests.integration.conftest import wait_for_service_ready

# Mark this module as an integration test
pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def install_airflow_service(ubuntu_docker_server):
    """Install and start the Airflow service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    # Load Airflow stack config
    config = load_config(get_stacks_path(), "/airflow", "mlox.3.1.3.yaml")

    bundle_added = add_service(infra, ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Airflow service from config")

    service = bundle_added.services[-1]

    # Setup and start the service
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
        # Allow some time for containers to become healthy
        # Downloading images and starting containers may take time

    for i in range(10):
        logger.info(f"Waiting 30s for Airflow service to stabilize... ({i + 1}/10)")
        time.sleep(30)

    yield bundle_added, service

    # Teardown after tests
    result = remove_service(infra, service.name)
    if not result.success:
        logger.warning(
            "Failed to remove service via application logic: %s", result.message
        )


@pytest.fixture(scope="module")
def install_airflow_secret_manager(install_airflow_service):
    """Install OpenBao beside Airflow so their live binding can be exercised."""

    bundle, airflow = install_airflow_service
    infra = airflow._service_lookup
    config = load_config(get_stacks_path(), "/openbao", "mlox.openbao.yaml")
    bundle_added = add_service(infra, bundle.server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add OpenBao service from config")
    openbao = bundle_added.services[-1]

    with bundle.server.get_server_connection() as conn:
        openbao.setup(conn)
        openbao.spin_up(conn)
    wait_for_service_ready(openbao, bundle, retries=6, interval=20, no_checks=True)

    yield bundle, airflow, openbao

    result = remove_service(infra, openbao.name)
    if not result.success:
        logger.warning(
            "Failed to remove OpenBao via application logic: %s", result.message
        )


def test_airflow_service_is_running(install_airflow_service):
    """Verify Airflow service is reported as running and exposes a URL."""
    bundle, service = install_airflow_service

    # perform a simple HTTP check against the webserver API if available
    web_url = service.service_urls.get("Airflow UI", None)
    assert web_url, "Airflow UI URL not found in service URLs"

    # Prefer rich health for services that advertise it, otherwise use check().
    retries = 40
    for i in range(retries):
        try:
            with bundle.server.get_server_connection() as conn:
                if ServiceCapability.HEALTH in (
                    getattr(service, "capabilities", set()) or set()
                ) and hasattr(service, "get_health"):
                    status = service.get_health(conn)
                else:
                    status = service.check(conn)
            if status.get("healthy") is True or status.get("status") == "running":
                break
            logger.warning(
                f"Retry {i + 1}/{retries} in 60s. Service state is {service.state} but Airflow service not yet up: {status}"
            )
            time.sleep(60)
        except Exception as e:
            status = {"status": "unknown", "error": str(e)}
            logger.warning(
                f"Retry {i + 1}/{retries} in 60s. Exception during status check: {e}"
            )

    assert status.get("healthy") is True or status.get("status") == "running"
    # state may be 'running' depending on service implementation
    assert service.state == "running"


def test_airflow_live_secret_manager_binding_and_unbinding(
    install_airflow_secret_manager,
):
    """Verify provider credentials reach Airflow and are revoked on unbind."""

    bundle, airflow, openbao = install_airflow_secret_manager
    compose_path = f"{airflow.target_path}/{airflow.target_docker_script}"
    env_path = f"{airflow.target_path}/{airflow.target_docker_env}"

    def scheduler_environment_test(conn, expression):
        inner = f"test {expression}"
        command = (
            f"docker compose --env-file {shlex.quote(env_path)} "
            f"-f {shlex.quote(compose_path)} exec -T airflow-scheduler "
            f"sh -c {shlex.quote(inner)}"
        )
        return airflow.exec.execute(
            conn,
            command,
            group=TaskGroup.CONTAINER_RUNTIME,
            sudo=True,
            description="Verify Airflow runtime secret-manager environment",
        )

    application = f"runtime-{airflow.uuid}"
    with bundle.server.get_server_connection() as conn:
        airflow.bind_secret_manager(openbao.uuid, conn)
        try:
            assert airflow.secret_manager_uuid == openbao.uuid
            assert application in openbao.application_credentials
            assert scheduler_environment_test(
                conn,
                '-n "$MLOX_SECRET_MANAGER_KEYFILE" '
                '&& test -n "$MLOX_SECRET_MANAGER_KEYFILE_PW"',
            ) == ""
        finally:
            airflow.unbind_secret_manager(conn)

        assert airflow.secret_manager_uuid is None
        assert application not in openbao.application_credentials
        assert scheduler_environment_test(
            conn,
            '-z "${MLOX_SECRET_MANAGER_KEYFILE:-}" '
            '&& test -z "${MLOX_SECRET_MANAGER_KEYFILE_PW:-}"',
        ) == ""
