import time
import logging
import grpc  # type: ignore
import pytest

from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from mlox.config import load_config, get_stacks_path
from mlox.infra import Infrastructure, Bundle
from tests.integration.conftest import wait_for_service_ready

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_otel_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/opentelemetry", "mlox.otel.0.127.0.yaml")
    bundle_added = infra.add_service(
        ubuntu_docker_server.ip,
        config,
        params={"${MLOX_RELIC_KEY}": "", "${MLOX_RELIC_ENDPOINT}": ""},
    )
    if not bundle_added:
        pytest.fail("Failed to add otel service from config")

    service = bundle_added.services[-1]
    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)
    # Initial stabilization wait while containers/images start up
    wait_for_service_ready(service, bundle, retries=6, interval=30, no_checks=True)

    yield bundle_added, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception:
            pass
        try:
            service.teardown(conn)
        except Exception:
            pass
    infra.remove_bundle(bundle_added)


def test_otel_service_is_running(install_otel_service):
    bundle, service = install_otel_service
    status = wait_for_service_ready(service, bundle, retries=10, interval=60)
    assert status.get("status") == "running"


# def test_otel_log_file_written(install_otel_service):
#     bundle, service = install_otel_service
#     # Ensure service is up before sending logs
#     wait_for_service_ready(service, bundle, retries=40, interval=15)

#     ssl_credentials = grpc.ssl_channel_credentials(
#         root_certificates=service.certificate.encode("utf-8")
#     )
#     resource = Resource.create({"service.name": "mlox.test"})
#     exporter = OTLPLogExporter(
#         endpoint=service.service_url, credentials=ssl_credentials, insecure=False
#     )
#     logger_provider = LoggerProvider(resource=resource)
#     logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
#     handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
#     otel_logger = logging.getLogger("test_otel_logger")
#     otel_logger.addHandler(handler)
#     otel_logger.setLevel(logging.INFO)
#     msg = "integration test log message"
#     otel_logger.info(msg)
#     time.sleep(3)
#     logger_provider.shutdown()

#     data = service.get_telemetry_data(bundle)
#     assert msg in data
