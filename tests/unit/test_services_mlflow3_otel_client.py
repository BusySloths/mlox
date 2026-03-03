from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from mlox.services.mlflow.docker_mlflow3 import MLFlow3DockerService
from mlox.services.otel.client import OTelClient


BASE = {
    "name": "svc",
    "service_config_id": "cfg",
    "template": "/tmp/compose.yaml",
    "target_path": "/tmp/stack",
}


class FakeExec:
    def __init__(self):
        self.calls = []
        self.service_states = {}
        self.files = {}

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def fs_create_dir(self, conn, path):
        self._record("fs_create_dir", path)

    def fs_copy(self, conn, src, dst):
        self._record("fs_copy", src, dst)

    def fs_create_empty_file(self, conn, path):
        self._record("fs_create_empty_file", path)

    def fs_append_line(self, conn, path, line):
        self._record("fs_append_line", path, line)

    def docker_up(self, conn, compose_path, env_path):
        self._record("docker_up", compose_path, env_path)

    def docker_down(self, conn, compose_path, remove_volumes=False):
        self._record("docker_down", compose_path, remove_volumes)

    def fs_delete_dir(self, conn, path):
        self._record("fs_delete_dir", path)


def test_mlflow3_docker_service_setup_check_and_models(monkeypatch):
    service = MLFlow3DockerService(**BASE, ui_user="ml", ui_pw="pw", port="5000")
    service.exec = FakeExec()
    conn = SimpleNamespace(host="example.test")
    service.setup(conn)

    assert service.service_url == "https://example.test:5000"
    assert service.service_ports["MLFlow Webserver"] == 5000
    assert service.service_urls["Dashboard"].startswith("https://")

    class _Model:
        def __init__(self, name, version):
            self.name = name
            self.description = ""
            self.version = version
            self.current_stage = "None"
            self.aliases = []
            self.status = "READY"
            self.tags = {}
            self.last_updated_timestamp = 1730000000000
            self.run_id = "run-1"

    class _Client:
        def search_registered_models(self, filter_string="", max_results=10):
            return [1, 2, 3]

        def search_model_versions(self, filter_string="", max_results=250):
            return [_Model("demo", "1")]

    class _Tracking:
        MlflowClient = _Client

    monkeypatch.setattr(
        "mlox.services.mlflow.docker_mlflow3.mlflow.set_registry_uri", lambda *_: None
    )
    monkeypatch.setattr("mlox.services.mlflow.docker_mlflow3.mlflow.tracking", _Tracking)

    status = service.check(conn)
    assert status["status"] == "running"
    rows = service.list_models()
    assert rows[0]["Model"] == "demo"

    secrets = service.get_secrets()
    assert secrets["username"] == "ml"
    assert secrets["insecure_tls"] == "true"

    assert service.spin_up(conn) is True
    assert service.spin_down(conn) is True
    service.teardown(conn)


def test_mlflow3_docker_service_fallback_paths(monkeypatch):
    service = MLFlow3DockerService(**BASE, ui_user="ml", ui_pw="pw", port="5000")
    service.exec = FakeExec()
    conn = SimpleNamespace(host="example.test")
    service.setup(conn)

    class _TrackingFailure:
        class MlflowClient:
            def __init__(self):
                raise RuntimeError("boom")

    monkeypatch.setattr(
        "mlox.services.mlflow.docker_mlflow3.mlflow.set_registry_uri", lambda *_: None
    )
    monkeypatch.setattr(
        "mlox.services.mlflow.docker_mlflow3.mlflow.tracking", _TrackingFailure
    )

    assert service.check(conn)["status"] == "unknown"
    assert service.list_models() == []


def test_otel_client_sends_metrics_traces_logs_and_shutdown(monkeypatch):
    class _Exporter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.shutdown_called = False

        def shutdown(self):
            self.shutdown_called = True

    class _Reader:
        def __init__(self, exporter, export_interval_millis):
            self.exporter = exporter
            self.export_interval_millis = export_interval_millis

    class _MeterProvider:
        def __init__(self, metric_readers, resource):
            self.metric_readers = metric_readers
            self.resource = resource

    class _Counter:
        def __init__(self):
            self.calls = []

        def add(self, value, attrs):
            self.calls.append((value, attrs))

    class _Histogram:
        def __init__(self):
            self.calls = []

        def record(self, value, attrs):
            self.calls.append((value, attrs))

    class _Gauge:
        def __init__(self):
            self.calls = []

        def set(self, value, attrs):
            self.calls.append((value, attrs))

    class _Meter:
        def __init__(self):
            self.counter = _Counter()
            self.hist = _Histogram()
            self.gauge = _Gauge()
            self.observable = []

        def create_counter(self, *args, **kwargs):
            return self.counter

        def create_histogram(self, *args, **kwargs):
            return self.hist

        def create_observable_gauge(self, *args, **kwargs):
            self.observable.append((args, kwargs))

        def create_gauge(self, *args, **kwargs):
            return self.gauge

    class _Span:
        def __init__(self):
            self.attrs = {}

        def set_attribute(self, key, value):
            self.attrs[key] = value

    class _SpanCtx:
        def __init__(self, span):
            self.span = span

        def __enter__(self):
            return self.span

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    class _Tracer:
        def __init__(self):
            self.spans = []

        def start_as_current_span(self, name):
            span = _Span()
            self.spans.append((name, span))
            return _SpanCtx(span)

    class _TracerProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class _BatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class _BatchLogRecordProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class _LoggerProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_log_record_processor(self, processor):
            self.processors.append(processor)

    class _LoggingHandler:
        def __init__(self, logger_provider):
            self.logger_provider = logger_provider

    meter = _Meter()
    tracer = _Tracer()

    monkeypatch.setattr("mlox.services.otel.client.grpc.ssl_channel_credentials", lambda root_certificates: "ssl-creds")
    monkeypatch.setattr("mlox.services.otel.client.OTLPMetricExporter", _Exporter)
    monkeypatch.setattr("mlox.services.otel.client.OTLPSpanExporter", _Exporter)
    monkeypatch.setattr("mlox.services.otel.client.OTLPLogExporter", _Exporter)
    monkeypatch.setattr("mlox.services.otel.client.PeriodicExportingMetricReader", _Reader)
    monkeypatch.setattr("mlox.services.otel.client.MeterProvider", _MeterProvider)
    monkeypatch.setattr("mlox.services.otel.client.TracerProvider", _TracerProvider)
    monkeypatch.setattr("mlox.services.otel.client.BatchSpanProcessor", _BatchSpanProcessor)
    monkeypatch.setattr("mlox.services.otel.client.BatchLogRecordProcessor", _BatchLogRecordProcessor)
    monkeypatch.setattr("mlox.services.otel.client.LoggerProvider", _LoggerProvider)
    monkeypatch.setattr("mlox.services.otel.client.LoggingHandler", _LoggingHandler)
    monkeypatch.setattr("mlox.services.otel.client.metrics.set_meter_provider", lambda provider: None)
    monkeypatch.setattr("mlox.services.otel.client.metrics.get_meter", lambda name: meter)
    monkeypatch.setattr("mlox.services.otel.client.trace.set_tracer_provider", lambda provider: None)
    monkeypatch.setattr("mlox.services.otel.client.trace.get_tracer", lambda name: tracer)

    client = OTelClient(
        collector_url="collector:4317",
        trusted_certs=b"cert-data",
        resource_attrs={"service.name": "unit-test"},
    )

    class _Logger:
        def __init__(self):
            self.calls = []

        def log(self, level, message, extra=None):
            self.calls.append((level, message, extra))

    fake_logger = _Logger()
    client.logger = fake_logger

    client.send_metric("requests.total", 3, {"env": "test"})
    client.send_histogram("latency.ms", 42.0, {"env": "test"})
    client.send_observable_gauge("cpu.pct", callback=lambda _: None)
    client.send_gauge("memory.pct", 0.7, {"env": "test"})
    client.send_span("job.run", {"ok": True})
    client.send_log("hello", severity="warning", attributes={"env": "test"})
    client.shutdown()

    assert meter.counter.calls == [(3, {"env": "test"})]
    assert meter.hist.calls == [(42.0, {"env": "test"})]
    assert meter.gauge.calls == [(0.7, {"env": "test"})]
    assert meter.observable
    assert tracer.spans[0][0] == "job.run"
    assert tracer.spans[0][1].attrs["ok"] is True
    assert fake_logger.calls
    assert client.metric_exporter.shutdown_called is True
    assert client.span_exporter.shutdown_called is True
    assert client.log_exporter.shutdown_called is True


def test_otel_client_init_from_service_secrets_dict(monkeypatch):
    class _Exporter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.shutdown_called = False

        def shutdown(self):
            self.shutdown_called = True

    class _Reader:
        def __init__(self, exporter, export_interval_millis):
            self.exporter = exporter
            self.export_interval_millis = export_interval_millis

    class _MeterProvider:
        def __init__(self, metric_readers, resource):
            self.metric_readers = metric_readers
            self.resource = resource

    class _TracerProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class _BatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class _BatchLogRecordProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class _LoggerProvider:
        def __init__(self, resource):
            self.resource = resource
            self.processors = []

        def add_log_record_processor(self, processor):
            self.processors.append(processor)

    class _LoggingHandler:
        def __init__(self, logger_provider):
            self.logger_provider = logger_provider

    class _Meter:
        def create_counter(self, *args, **kwargs):
            return object()

        def create_histogram(self, *args, **kwargs):
            return object()

        def create_observable_gauge(self, *args, **kwargs):
            return None

        def create_gauge(self, *args, **kwargs):
            return object()

    monkeypatch.setattr(
        "mlox.services.otel.client.grpc.ssl_channel_credentials",
        lambda root_certificates: "ssl-creds",
    )
    monkeypatch.setattr("mlox.services.otel.client.OTLPMetricExporter", _Exporter)
    monkeypatch.setattr("mlox.services.otel.client.OTLPSpanExporter", _Exporter)
    monkeypatch.setattr("mlox.services.otel.client.OTLPLogExporter", _Exporter)
    monkeypatch.setattr("mlox.services.otel.client.PeriodicExportingMetricReader", _Reader)
    monkeypatch.setattr("mlox.services.otel.client.MeterProvider", _MeterProvider)
    monkeypatch.setattr("mlox.services.otel.client.TracerProvider", _TracerProvider)
    monkeypatch.setattr("mlox.services.otel.client.BatchSpanProcessor", _BatchSpanProcessor)
    monkeypatch.setattr(
        "mlox.services.otel.client.BatchLogRecordProcessor", _BatchLogRecordProcessor
    )
    monkeypatch.setattr("mlox.services.otel.client.LoggerProvider", _LoggerProvider)
    monkeypatch.setattr("mlox.services.otel.client.LoggingHandler", _LoggingHandler)
    monkeypatch.setattr("mlox.services.otel.client.metrics.set_meter_provider", lambda provider: None)
    monkeypatch.setattr("mlox.services.otel.client.metrics.get_meter", lambda name: _Meter())
    monkeypatch.setattr("mlox.services.otel.client.trace.set_tracer_provider", lambda provider: None)
    monkeypatch.setattr("mlox.services.otel.client.trace.get_tracer", lambda name: object())

    service_secrets = {
        "otel_client_connection": {
            "collector_url": "https://collector.example:4317",
            "trusted_certs": "PEM-CONTENT",
            "insecure_tls": False,
            "protocol": "otlp_grpc",
        }
    }
    client = OTelClient(
        otel_secret=service_secrets,
        resource_attrs={"service.name": "unit-test"},
    )

    assert client.collector_url == "https://collector.example:4317"
    assert client.trusted_certs == b"PEM-CONTENT"
    assert client.metric_exporter.kwargs["endpoint"] == "https://collector.example:4317"
    assert client.metric_exporter.kwargs["credentials"] == "ssl-creds"
    assert client.metric_exporter.kwargs["insecure"] is False
