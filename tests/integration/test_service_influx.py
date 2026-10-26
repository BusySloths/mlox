from tests.integration.helpers import add_service, remove_service
import logging
import pytest
import requests

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle

from tests.integration.conftest import wait_for_service_ready


pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def install_influx_service(ubuntu_docker_server):
    """Install and start the InfluxDB service on the provided server."""
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/influx", "mlox.influx.3.12.0-core.yaml")

    bundle_added = add_service(infra, ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add InfluxDB service from config")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=30, no_checks=True)

    yield bundle_added, service

    result = remove_service(infra, service.name)
    if not result.success:
        logger.warning("Failed to remove service via application logic: %s", result.message)


def test_influx_service_is_running(install_influx_service):
    bundle, service = install_influx_service
    wait_for_service_ready(service, bundle, retries=60, interval=10)

    status = {}
    try:
        with bundle.server.get_server_connection() as conn:
            status = service.check(conn)
    except Exception as e:
        logger.error(f"Error checking InfluxDB service status: {e}")

    assert status.get("status", None) == "running"


def test_influxdb_accepts_collector_signal_measurements(
    install_influx_service, tmp_path
):
    """Core accepts the line protocol emitted for metrics, logs, and traces.

    The contrib InfluxDB exporter uses Core's v2-compatible write endpoint;
    the bucket parameter maps directly to the Core database.
    """
    bundle, service = install_influx_service
    wait_for_service_ready(service, bundle, retries=60, interval=10)

    connection = service.get_secrets()["influx_connection"]
    endpoint = f"{connection['url']}/api/v2/write"
    certificate_path = tmp_path / "influx-ca.pem"
    certificate_path.write_text(connection["certificate"], encoding="utf-8")
    payload = "\n".join(
        (
            "collector_metric,service.name=integration value=1i",
            "logs,service.name=integration body=\"log\"",
            "spans,service.name=integration name=\"span\"",
        )
    )
    response = requests.post(
        endpoint,
        params={"org": "mlox", "bucket": connection["database"], "precision": "ns"},
        headers={
            "Authorization": f"Token {connection['token']}",
            "Content-Type": "text/plain",
        },
        data=payload.encode(),
        verify=str(certificate_path),
        timeout=20,
    )
    assert response.status_code == 204, response.text

    query = requests.post(
        f"{connection['url']}/api/v3/query_sql",
        headers={"Authorization": f"Bearer {connection['token']}"},
        json={"db": connection["database"], "q": "SELECT table_name FROM information_schema.tables", "format": "json"},
        verify=str(certificate_path),
        timeout=20,
    )
    query.raise_for_status()
    rows = query.json()
    names = {row["table_name"] for row in rows}
    assert {"collector_metric", "logs", "spans"} <= names
