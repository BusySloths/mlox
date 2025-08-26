import grpc  # type: ignore
import time
import logging

from typing import Dict, Any, Optional

from opentelemetry import metrics, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor


class OTelClient:
    def __init__(
        self, collector_url: str, trusted_certs: bytes, resource_attrs: Dict[str, Any]
    ):
        self.collector_url = collector_url
        self.trusted_certs = trusted_certs
        self.resource = Resource.create(resource_attrs)
        self.ssl_credentials = grpc.ssl_channel_credentials(
            root_certificates=trusted_certs
        )
        self._setup_metrics()
        self._setup_tracing()
        self._setup_logs()

    def _setup_logs(self):
        # Configure the OTLP Log Exporter
        self.log_exporter = OTLPLogExporter(
            endpoint=self.collector_url,
            credentials=self.ssl_credentials,
            insecure=False,
        )
        # Configure the LoggerProvider
        self.logger_provider = LoggerProvider(resource=self.resource)
        self.logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(self.log_exporter)
        )
        # Set up the Python logging module to use OpenTelemetry
        self.logging_handler = LoggingHandler(logger_provider=self.logger_provider)
        logging.basicConfig(
            level=logging.INFO,
            format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[self.logging_handler],
        )
        self.logger = logging.getLogger("otel_logger")

    def _setup_metrics(self):
        self.metric_exporter = OTLPMetricExporter(
            endpoint=self.collector_url,
            credentials=self.ssl_credentials,
            insecure=False,
        )
        self.metric_reader = PeriodicExportingMetricReader(
            exporter=self.metric_exporter,
            export_interval_millis=1000,
        )
        self.meter_provider = MeterProvider(
            metric_readers=[self.metric_reader], resource=self.resource
        )
        metrics.set_meter_provider(self.meter_provider)
        self.meter = metrics.get_meter(__name__)

    def _setup_tracing(self):
        self.span_exporter = OTLPSpanExporter(
            endpoint=self.collector_url,
            credentials=self.ssl_credentials,
            insecure=False,
        )
        self.tracer_provider = TracerProvider(resource=self.resource)
        self.tracer_provider.add_span_processor(BatchSpanProcessor(self.span_exporter))
        trace.set_tracer_provider(self.tracer_provider)
        self.tracer = trace.get_tracer(__name__)

    def send_metric(
        self, name: str, value: float, attributes: Optional[Dict[str, Any]] = None
    ):
        counter = self.meter.create_counter(
            name, unit="1", description="Custom Counter"
        )
        counter.add(value, attributes or {})

    def send_histogram(
        self, name: str, value: float, attributes: Optional[Dict[str, Any]] = None
    ):
        histogram = self.meter.create_histogram(
            name, description="Custom Histogram", unit="ms"
        )
        histogram.record(value, attributes or {})

    def send_observable_gauge(
        self,
        name: str,
        callback,
        unit: str = "%",
        description: str = "Observable Gauge",
    ):
        self.meter.create_observable_gauge(
            name,
            callbacks=[callback],
            unit=unit,
            description=description,
        )

    def send_gauge(
        self,
        name: str,
        value: float,
        attributes: Optional[Dict[str, Any]] = None,
        unit: str = "%",
        description: str = "Gauge",
    ):
        gauge = self.meter.create_gauge(name, unit=unit, description=description)
        gauge.set(value, attributes or {})

    def send_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        with self.tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(k, v)

    def send_log(
        self,
        message: str,
        severity: str = "INFO",
        attributes: Optional[Dict[str, Any]] = None,
    ):
        level = getattr(logging, severity.upper(), logging.INFO)
        self.logger.log(level, message, extra=attributes or {})

    def shutdown(self):
        self.metric_exporter.shutdown()
        self.span_exporter.shutdown()
        self.log_exporter.shutdown()
