import os
import grpc  # type: ignore

from typing import Iterable

from opentelemetry import metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.metrics import Observation, CallbackOptions  # type: ignore
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter


from mlox.session import MloxSession


password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
# Make sure your environment variable is set!
if not password:
    print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    exit(1)
session = MloxSession("mlox", password)
infra = session.infra

monitors = infra.filter_by_group("monitor")
if len(monitors) == 0:
    print("No monitors found.")
    exit()
# collector_url = f"{infra.bundles[0].server.ip}:{infra.bundles[0].services[2].service.service_ports['OTLP gRPC receiver']}"
# trusted_certs = infra.bundles[0].services[2].service.certificate.encode("utf-8")
collector_url = monitors[0].service_url
trusted_certs = monitors[0].certificate.encode("utf-8")


# Define the resource with service name and other attributes
resource = Resource.create(
    {
        "service.name": "my-super-python-service",  # Service name for tracing and metrics
        "service.version": "2.0.0",
        "service.instance.id": "instance-1",
    }
)

# Create SSL credentials for OTLP exporters
ssl_credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

# === METRICS SETUP ===
# Configure the OTLP Metric Exporter
metric_exporter = OTLPMetricExporter(
    endpoint=collector_url, credentials=ssl_credentials, insecure=False
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

print("WAITING...")
import time

time.sleep(5)
metric_exporter.shutdown()
print("FINAL")
