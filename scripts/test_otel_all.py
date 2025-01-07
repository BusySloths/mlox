import os
import grpc  # type: ignore
import logging

from typing import Iterable

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.metrics import Observation, CallbackOptions  # type: ignore
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor  # type: ignore

# Define the resource with service name and other attributes
resource = Resource.create(
    {
        "service.name": "my-super-python-service",  # Service name for tracing and metrics
        "service.version": "2.0.0",
        "service.instance.id": "instance-1",
    }
)

collector_url = os.environ["TEST_OTEL_URL"]


# === TRACING SETUP ===
# Path to the self-signed certificate (if using TLS)
cert_path = "cert-otel.pem"

# Load the self-signed certificate
with open(cert_path, "rb") as f:
    trusted_certs = f.read()

# Create SSL credentials for OTLP exporters
ssl_credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

# Configure the OTLP Trace Exporter
trace_exporter = OTLPSpanExporter(
    endpoint=collector_url,  # Replace with your OpenTelemetry Collector's IP
    credentials=ssl_credentials,
    insecure=False,
)

# Configure the TracerProvider
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
trace.set_tracer_provider(tracer_provider)

# Create a tracer
tracer = trace.get_tracer(__name__)


# === METRICS SETUP ===
# Configure the OTLP Metric Exporter
metric_exporter = OTLPMetricExporter(
    endpoint=collector_url,  # Replace with your OpenTelemetry Collector's IP
    credentials=ssl_credentials,
    insecure=False,
)


# Configure a Metric Reader with a shorter export interval
metric_reader = PeriodicExportingMetricReader(
    exporter=metric_exporter,
    export_interval_millis=1000,  # Export every 5 seconds
)

# Configure the MeterProvider
meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
metrics.set_meter_provider(meter_provider)

# Create a Meter
meter = metrics.get_meter(__name__)

# Create a Counter Metric
request_counter = meter.create_counter(
    "my_requests_only_increasing", unit="1", description="Counts the number of requests"
)
# Increment the counter
request_counter.add(1, {"http.method": "GET", "http.route": "/example"})
request_counter.add(3, {"http.method": "GET", "http.route": "/example"})
request_counter.add(1, {"http.method": "GET", "http.route": "/example"})
request_counter.add(1, {"http.method": "GET", "http.route": "/example"})

# Create a Histogram
request_latency = meter.create_histogram(
    "my_request_latency", description="Records the latency of API requests", unit="ms"
)
# Record values in the Histogram
request_latency.record(100, {"http.method": "GET", "http.route": "/example"})
request_latency.record(200, {"http.method": "POST", "http.route": "/upload"})


# Create an Observable Gauge Metric
def cpu_utilization_callback(
    options: CallbackOptions,
) -> Iterable[Observation]:  # Simulating a CPU utilization value
    print("CALL CPU METRIC")
    return [Observation(42.5, {"host.name": "localhost"})]
    # yield metrics.Observation(42.5, {"host.name": "localhost"})


meter.create_observable_gauge(
    "cpu_utilization_async",
    callbacks=[cpu_utilization_callback],
    unit="%",
    description="Current CPU utilization",
)

gauge = meter.create_gauge(
    "cpu_utilization_sequential",
    unit="%",
    description="Current CPU utilization",
)
gauge.set(10, {"attrib1": 10})
gauge.set(-10, {"attrib1": -10})
gauge.set(2, {"attrib1": 2})


# === LOGGING SETUP ===
# Configure the OTLP Log Exporter
log_exporter = OTLPLogExporter(
    endpoint=collector_url,  # Replace with your OpenTelemetry Collector's IP
    credentials=ssl_credentials,
    insecure=False,
)

# Configure the LoggerProvider
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

# Set up the Python logging module to use OpenTelemetry
logging_handler = LoggingHandler(logger_provider=logger_provider)
logging.basicConfig(level=logging.INFO, handlers=[logging_handler])

# Get a logger
logger = logging.getLogger(__name__)

# === EXAMPLE USAGE ===
# Log a message
logger.info("This is a SUPER test log message.")
logger.error("This is an ERROR test log message.")

# Start a span
with tracer.start_as_current_span("example-span") as span:
    span.add_event("This is a test event inside the span.")
    print("Span created with service name, metrics, and logs.")

print("WAITING...")

import time

time.sleep(10)

print("DONE")

# Shutdown exporters
os.environ["GRPC_TRACE"] = "all"
os.environ["GRPC_VERBOSITY"] = "DEBUG"
trace_exporter.shutdown()
metric_exporter.shutdown()
log_exporter.shutdown()
print("FINAL")
