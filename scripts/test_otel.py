import os
import grpc  # type: ignore
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore


# NOTES:
# - check the certificate on a remote collector:
#   openssl s_client -connect <ip-address>:4317
# - check remote ports:
#   nc -zv <ip-address> 4317

# Set the URL of the OpenTelemetry collector
collector_url = os.environ["TEST_OTEL_URL"]

# Path to the self-signed certificate of the mlflow server
cert_path = "cert.pem"

# Load the certificate
with open(cert_path, "rb") as f:
    trusted_certs = f.read()

# Create SSL credentials with the self-signed certificate
ssl_credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

# Create the OTLP exporter using the gRPC channel with SSL credentials
otlp_exporter = OTLPSpanExporter(
    endpoint=collector_url, credentials=ssl_credentials, insecure=False
)

# Set up the trace provider and add the span processor
span_processor = BatchSpanProcessor(otlp_exporter)
provider = TracerProvider()
provider.add_span_processor(span_processor)
trace.set_tracer_provider(provider)


# Example tracing code
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("test-span"):
    print("Span created")
