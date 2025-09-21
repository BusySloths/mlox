import uuid
import logging
from pathlib import Path

import pytest

from kafka import KafkaConsumer, KafkaProducer  # type: ignore

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure

from tests.integration.conftest import wait_for_service_ready

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def install_kafka_service(ubuntu_docker_server):
    infra = Infrastructure()
    bundle = Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server)
    infra.bundles.append(bundle)

    config = load_config(get_stacks_path(), "/kafka", "mlox.kafka.3.7.0.yaml")

    bundle_added = infra.add_service(ubuntu_docker_server.ip, config, params={})
    if not bundle_added:
        pytest.skip("Failed to add Kafka service from config")

    bundle = bundle_added
    service = bundle.services[-1]

    with ubuntu_docker_server.get_server_connection() as conn:
        service.setup(conn)
        service.spin_up(conn)

    wait_for_service_ready(service, bundle, retries=3, interval=20, no_checks=True)

    yield bundle, service

    with ubuntu_docker_server.get_server_connection() as conn:
        try:
            service.spin_down(conn)
        except Exception:
            pass
        try:
            service.teardown(conn)
        except Exception:
            pass
    infra.remove_bundle(bundle)


def _write_certificate(tmp_path: Path, certificate: str) -> Path:
    cafile = tmp_path / "kafka-ca.pem"
    # cafile.write_text(certificate)
    with open(cafile, "w") as f:
        f.write(certificate)
    return cafile


def test_kafka_service_is_installed(install_kafka_service):
    _, service = install_kafka_service
    assert service.service_url
    assert service.state == "running"


def test_kafka_service_is_running(install_kafka_service):
    bundle, service = install_kafka_service
    status = wait_for_service_ready(service, bundle, retries=6, interval=10)
    assert status.get("status") == "running"


@pytest.mark.parametrize("topic", ["mlox-integration-topic"])
def test_kafka_basic_read_write(install_kafka_service, tmp_path, topic):
    bundle, service = install_kafka_service
    status = wait_for_service_ready(
        service, bundle, retries=6, interval=10, no_checks=True
    )
    # assert status.get("status") == "running"

    cafile = _write_certificate(tmp_path, service.certificate)
    bootstrap = f"{bundle.server.ip}:{service.service_ports['Kafka SSL']}"
    message = b"hello from mlox kafka"

    logger.info(f"Using bootstrap server: {bootstrap}")
    logger.info(f"Using cafile: {str(cafile)}")
    logger.info(f"Using topic: {topic}")
    logger.info(f"Using message: {message}")
    assert service.certificate is not None
    assert service.service_ports.get("Kafka SSL") is not None
    producer = KafkaProducer(
        bootstrap_servers=[bootstrap],
        security_protocol="SSL",
        ssl_cafile=str(cafile),
        ssl_check_hostname=False,
    )
    future = producer.send(topic, message)
    future.get(timeout=30)
    producer.flush()
    producer.close()

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=[bootstrap],
        security_protocol="SSL",
        ssl_cafile=str(cafile),
        ssl_check_hostname=False,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        group_id=f"mlox-integration-{uuid.uuid4().hex[:8]}",
        consumer_timeout_ms=15000,
    )

    received = [record.value for record in consumer]
    consumer.close()

    assert message in received
