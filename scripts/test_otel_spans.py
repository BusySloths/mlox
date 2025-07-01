import os
import grpc  # type: ignore
import time
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore

from mlox.session import MloxSession

# NOTES:
# - check the certificate on a remote collector:
#   openssl s_client -connect <ip-address>:4317
# - check remote ports:
#   nc -zv <ip-address> 4317

# Define the service name as part of the resource
resource = Resource.create(
    {
        "service.name": "my-python-service",  # Replace with your desired service name
        "service.version": "1.0.1",  # Optional: Add version or other attributes
        "service.instance.id": "instance-1",  # Optional: Unique instance identifier
    }
)

# Set the URL of the OpenTelemetry collector


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

# # Path to the self-signed certificate of the mlflow server
# cert_path = "cert-otel.pem"

# # Load the certificate
# with open(cert_path, "rb") as f:
#     trusted_certs = f.read()

# Create SSL credentials with the self-signed certificate
ssl_credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

# Create the OTLP exporter using the gRPC channel with SSL credentials
otlp_exporter = OTLPSpanExporter(
    endpoint=collector_url, credentials=ssl_credentials, insecure=False
)

# Set up the trace provider and add the span processor
span_processor = BatchSpanProcessor(otlp_exporter)
provider = TracerProvider(resource=resource)
provider.add_span_processor(span_processor)
trace.set_tracer_provider(provider)

# Example tracing code
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("test-span-2") as span:
    print("Span created")
    time.sleep(1)
    span.add_event("event-1")
    time.sleep(2)
    print("Event created")
    with tracer.start_as_current_span("child-test-span-2") as span:
        print("Child Span created")
        time.sleep(1.5)
        span.add_event("child-event-2")
        print("Child Event created")
        time.sleep(2.5)

# os.environ["GRPC_TRACE"] = "all"
# os.environ["GRPC_VERBOSITY"] = "DEBUG"

# # import time

# # time.sleep(10)  # Allow

# otlp_exporter.shutdown()  # Explicitly shut down the exporter
# print("Forcing flush of telemetry data...")
# try:
#     # provider.force_flush() can take a timeout.
#     # Increase if necessary, default is 30 seconds (30000 ms).
#     provider.force_flush(timeout_millis=10000)  # e.g., 10 seconds
#     print("Flush attempt complete.")
# except Exception as e:
#     print(f"Error during force_flush: {e}")

# print("Shutting down TracerProvider...")
# provider.shutdown()
# print("TracerProvider shutdown complete.")
