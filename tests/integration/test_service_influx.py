import logging
import pytest
from influxdb import InfluxDBClient

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

    config = load_config(get_stacks_path(), "/influx", "mlox.influx.1.11.8.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add InfluxDB service from config")

    service = bundle_added.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=6, interval=30, no_checks=True)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service spin_down for teardown: {e}")
        try:
            service.teardown(conn)
        except Exception as e:
            logger.warning(f"Ignoring error during service teardown: {e}")
    infra.remove_bundle(bundle_added)


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


def test_influxdb_write_and_read(install_influx_service):
    bundle, service = install_influx_service
    wait_for_service_ready(service, bundle, retries=60, interval=10)

    host = bundle.server.ip
    port = service.port
    user = service.user
    password = service.pw
    dbname = "test_integration_db"

    client = InfluxDBClient(host, port, user, password, dbname, ssl=True, verify_ssl=False)
    client.create_database(dbname)

    json_body = [
        {
            "measurement": "cpu_load_short",
            "tags": {"host": "server01", "region": "us-west"},
            "fields": {"Float_value": 0.64},
        }
    ]
    client.write_points(json_body)

    result = list(client.query("select * from cpu_load_short").get_points())
    assert result, "Expected at least one data point from InfluxDB"
