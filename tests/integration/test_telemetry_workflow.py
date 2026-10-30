"""Real Docker integration coverage for collector, Influx and model telemetry.

Run on the Multipass host with ``pytest tests/integration/test_telemetry_workflow.py
-m integration --run-integration``. The gateway workflow builds several images
and needs the same network access and resources as the MLflow integration tests.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

import mlflow
import pytest
import requests

from mlox.config import get_stacks_path, load_config
from mlox.infra import Bundle, Infrastructure
from mlox.services.influx.client import InfluxClient
from mlox.services.otel.client import OTelClient
from tests.integration.conftest import wait_for_service_ready
from tests.integration.helpers import add_service, remove_service
from tests.integration.test_service_mlflow import install_mlflow_service  # noqa: F401

pytestmark = pytest.mark.integration
pytest_plugins = ["tests.integration.test_service_mlflow"]
logger = logging.getLogger(__name__)


def _add_running(infra, server, folder, filename, params, installed):
    config = load_config(get_stacks_path(), f"/{folder}", filename)
    assert config is not None
    bundle = add_service(infra, server.ip, config, params=params)
    assert bundle is not None, f"Failed to add {filename}"
    service = bundle.services[-1]
    installed.append(service)
    with server.get_server_connection() as conn:
        service.setup(conn)
        assert service.spin_up(conn)
    assert wait_for_service_ready(service, bundle, retries=60, interval=5).get("status") == "running"
    return service


def _cleanup(infra, installed):
    for service in reversed(installed):
        try:
            result = remove_service(infra, service.name)
            if not result.success:
                logger.error("Could not remove %s: %s", service.name, result.message)
        except Exception:
            logger.exception("Could not remove %s", service.name)


def _create_telemetry(infra, server, installed):
    influx = _add_running(infra, server, "influx", "mlox.influx.3.12.0-core.yaml", {}, installed)
    otel = _add_running(infra, server, "otel", "mlox.otel.0.146.1.yaml", {
        "${MLOX_OTEL_INFLUX_SERVICE_UUID}": influx.uuid,
    }, installed)
    connection = influx.get_secrets()["influx_connection"]
    client = InfluxClient(
        url=connection["url"], token=connection["token"], database=connection["database"],
        certificate=connection["certificate"].encode(),
    )
    return influx, otel, client


def _wait_for(predicate, description, timeout=90):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(2)
    pytest.fail(f"Timed out waiting for {description}; last query error: {last_error}")


def test_collector_exports_all_signals_and_preserves_tls_on_update(ubuntu_docker_server):
    infra = Infrastructure()
    infra.bundles.append(Bundle(name=ubuntu_docker_server.ip, server=ubuntu_docker_server))
    installed = []
    client = None
    try:
        _, otel, influx = _create_telemetry(infra, ubuntu_docker_server, installed)
        original_certificate = otel.certificate
        client = OTelClient(
            collector_url=otel.service_url, trusted_certs=original_certificate,
            resource_attrs={"service.name": "mlox-integration-probe"},
        )
        run_id = uuid.uuid4().hex

        def emit(phase):
            marker = f"{run_id}-{phase}"
            with client.span("mlox.integration.span", attributes={"mlox.integration.id": marker}):
                pass
            client.send_metric("mlox.integration.probes", 1, {"mlox.integration.id": marker})
            client.send_log(f"mlox integration {marker}")
            client.tracer_provider.force_flush()
            client.meter_provider.force_flush()
            client.logger_provider.force_flush()
            return marker

        def received(marker):
            tables = influx.measurements(max_rows=500)
            metrics = influx.recent_metrics(measurement_names=tables, max_tables=20, limit=100)
            spans = influx.recent_spans(measurement_names=tables, limit=100)
            logs = influx.recent_logs(measurement_names=tables, limit=100)
            return all(any(marker in str(row) for row in rows) for rows in (metrics, spans, logs))

        before = emit("before")
        _wait_for(lambda: received(before), "all signals before collector update")
        with ubuntu_docker_server.get_server_connection() as conn:
            result = otel.update_destinations(conn, diagnostic_exporter=True)
            deployed_certificate = otel.exec.fs_read_file(conn, f"{otel.target_path}/cert.pem", format="txt/plain")
        assert result["updated"], result
        assert otel.certificate == original_certificate == deployed_certificate
        after = emit("after")
        _wait_for(lambda: received(after), "all signals after collector update using the original certificate")
    finally:
        if client is not None:
            client.shutdown()
            client.logger.removeHandler(client.logging_handler)
        _cleanup(infra, installed)


def test_operations_demo_gateway_exports_pipeline_to_influx(
    ubuntu_docker_server, install_mlflow_service, monkeypatch
):
    """Register the actual demo, deploy the stack, predict, and query its spans."""
    from examples.operations_demo.model import OperationsDemoModel, demonstration_batch
    from examples.operations_demo.register import _serving_signature
    from mlox.services.mlflow.mlops import MLFlowDeployableModelService

    bundle, registry = install_mlflow_service
    assert wait_for_service_ready(registry, bundle, retries=60, interval=5).get("status") == "running"
    for key, value in {
        "MLFLOW_URI": registry.service_url, "MLFLOW_TRACKING_URI": registry.service_url,
        "MLFLOW_TRACKING_USERNAME": registry.ui_user, "MLFLOW_TRACKING_PASSWORD": registry.ui_pw,
        "MLFLOW_TRACKING_INSECURE_TLS": "true",
    }.items():
        monkeypatch.setenv(key, value)
    mlflow.set_tracking_uri(registry.service_url)
    mlflow.set_registry_uri(registry.service_url)
    root = Path(__file__).resolve().parents[2]
    model_name = f"mlox-operations-integration-{uuid.uuid4().hex[:8]}"
    model = MLFlowDeployableModelService(
        OperationsDemoModel(), model_name, code_paths=[str(root / "mlox"), str(root / "examples")],
    )
    model.set_registered_model_name(model_name)
    info = model.track_model(input_example=demonstration_batch(8), inference_params={"corrupt": False}, signature=_serving_signature())
    version = str(info.registered_model_version)
    assert version and version != "None"

    infra = Infrastructure()
    infra.bundles.append(bundle)
    infra.hydrate_runtime()
    installed = []
    try:
        _, otel, influx = _create_telemetry(infra, ubuntu_docker_server, installed)
        gateway_config = load_config(get_stacks_path(), "/mlflow_gateway", "mlox.mlflow_gateway.3.8.1.yaml")
        gateway_bundle = add_service(infra, ubuntu_docker_server.ip, gateway_config, params={
            "${TRACKING_URI}": registry.service_url, "${TRACKING_USER}": registry.ui_user,
            "${TRACKING_PW}": registry.ui_pw, "${GATEWAY_REQUIREMENTS_TXT}": "",
            "${MODEL_REGISTRY_UUID}": registry.uuid,
        })
        assert gateway_bundle is not None
        gateway = gateway_bundle.services[-1]
        installed.append(gateway)
        gateway.telemetry_uuid = otel.uuid
        with ubuntu_docker_server.get_server_connection() as conn:
            gateway.setup(conn)
            assert gateway.spin_up(conn)
        assert wait_for_service_ready(gateway, bundle, retries=60, interval=10).get("status") == "running"
        frame = demonstration_batch(8)
        pipeline_id = uuid.uuid4().hex
        def predict(pipeline_id):
            response = requests.post(
                f"{gateway.service_url}/prod/predict",
                json={"dataframe_split": {"columns": list(frame.columns), "data": frame.values.tolist()},
                      "params": {"corrupt": False}, "registry_model_name": model_name, "registry_model_version": version},
                auth=(gateway.user, gateway.pw),
                headers={"Host": gateway.service_url.split("//", 1)[1].split(":", 1)[0],
                         "X-MLOX-Pipeline-ID": pipeline_id, "X-MLOX-Pipeline-Name": "operations-integration"},
                verify=False, timeout=120,
            )
            response.raise_for_status()
            data = response.json().get("data")
            assert data and "prediction" in data[0], data

        def pipeline_received(pipeline_id):
            spans = influx.recent_spans(since_seconds=600, limit=500)
            matching = [row for row in spans if pipeline_id in str(row)]
            roots = {str(row.get("trace_id") or row.get("traceId")) for row in matching if "mlox.model.live_predict" in str(row)}
            steps = {str(row.get("trace_id") or row.get("traceId")) for row in matching if "mlox.model.step" in str(row) and "mlox.step.path" in str(row)}
            return bool((roots & steps) - {"None", ""})

        predict(pipeline_id)
        _wait_for(lambda: pipeline_received(pipeline_id), "demo model root and step spans in Influx", timeout=120)
        original_certificate = otel.certificate
        with ubuntu_docker_server.get_server_connection() as conn:
            result = otel.update_destinations(conn, diagnostic_exporter=True)
        assert result["updated"], result
        assert otel.certificate == original_certificate
        pipeline_id = uuid.uuid4().hex
        predict(pipeline_id)
        _wait_for(lambda: pipeline_received(pipeline_id), "gateway model spans after collector update", timeout=120)
    finally:
        _cleanup(infra, installed)
