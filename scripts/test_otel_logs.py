import os
import time
import grpc  # type: ignore
import logging


from opentelemetry.sdk.resources import Resource

from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler, LogRecord
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry._logs.severity import SeverityNumber
from opentelemetry.trace import get_current_span

from mlox.session import MloxSession

password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
# Make sure your environment variable is set!
if not password:
    print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    exit(1)
session = MloxSession("mlox", password)
session.load_infrastructure()
infra = session.infra


monitors = infra.filter_by_group("monitor")
if len(monitors) == 0:
    print("No monitors found.")
    exit()
# collector_url = f"{infra.bundles[0].server.ip}:{infra.bundles[0].services[2].service.service_ports['OTLP gRPC receiver']}"
# trusted_certs = infra.bundles[0].services[2].service.certificate.encode("utf-8")
collector_url = monitors[0].service.service_url
trusted_certs = monitors[0].service.certificate.encode("utf-8")

# Define the resource with service name and other attributes
resource = Resource.create(
    {
        "service.name": "my-super-python-service",  # Service name for tracing and metrics
        "service.version": "2.0.0",
        "service.instance.id": "instance-2",
    }
)

# Create SSL credentials for OTLP exporters
ssl_credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

# === LOGGING SETUP ===
# Configure the OTLP Log Exporter
log_exporter = OTLPLogExporter(
    endpoint=collector_url, credentials=ssl_credentials, insecure=False
)


# Configure the LoggerProvider
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

# Set up the Python logging module to use OpenTelemetry
logging_handler = LoggingHandler(logger_provider=logger_provider)
logging.basicConfig(level=logging.DEBUG, handlers=[logging_handler])

# Get a logger
logger = logging.getLogger(__name__)

# === EXAMPLE USAGE ===
# Log a message
logger.log(logging.DEBUG, "This is a test log message.")
logger.log(logging.ERROR, "This is a test log message.")
logger.log(logging.INFO, "This is a test log message.")
logger.debug("This is a SUPER test log message.")
logger.info("This is a SUPER test log message.")
logger.error("This is an ERROR test log message.")


# === EXAMPLE OF DIRECT LOG EMISSION ===
# Get a logger directly from the provider
otel_logger = logger_provider.get_logger("my.direct.logger", "1.0.0")

# Emit a log record directly

span = get_current_span()
ctx = span.get_span_context()

record = LogRecord(
    timestamp=int(time.time() * 1e9),
    body="Log WITH trace context",
    severity_text="INFO",
    severity_number=SeverityNumber.INFO,
    trace_id=ctx.trace_id,
    span_id=ctx.span_id,
    trace_flags=ctx.trace_flags,
    attributes={"component": "test-logger"},
)

otel_logger.emit(record)
print("Direct log message emitted.")

print("WAITING...")

time.sleep(3)
# log_exporter.shutdown()
logger_provider.shutdown()

print("FINAL")
