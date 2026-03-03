"""WORK IN PROGRESS: Educational OTel client example for MLOX OpenTelemetry Collector.

What this demonstrates:
- Discover an OTEL collector service from your active MLOX infra
- Build an ``OTelClient`` from service secrets
- Emit spans, metrics, and logs in one short run

Prerequisites:
- Environment variables: ``MLOX_PROJECT_NAME`` and ``MLOX_PROJECT_PASSWORD``
- A running OpenTelemetry Collector service in your project
"""

from __future__ import annotations

import time

from mlox.session import MloxSession
from mlox.services.otel.client import OTelClient

from examples.load_project_data import load_mlox_session


def _otel_client(session: MloxSession) -> OTelClient:
    monitors = session.infra.filter_by_group("monitor")
    if not monitors:
        raise RuntimeError("No monitor services found. Start an OTEL collector first.")

    for service in monitors:
        if service.state == "running":
            secrets = service.get_secrets()
            client = OTelClient(
                otel_secret=secrets,
                resource_attrs={
                    "service.name": "mlox.examples.otel-client",
                    "service.version": "1.0.0",
                    "service.instance.id": "example-instance-1",
                    "deployment.environment": "dev",
                },
            )
            return client

    raise RuntimeError("No running monitor service found.")


def main() -> None:
    session = load_mlox_session()
    client = _otel_client(session)

    # Traces: parent + nested span
    client.send_span(
        "examples.otel.parent_span",
        {
            "workflow.step": "start",
            "example": True,
        },
    )
    client.send_span(
        "examples.otel.child_span",
        {
            "workflow.step": "child",
            "latency.bucket": "fast",
        },
    )

    # Metrics: counter, histogram, gauge
    client.send_metric(
        "examples.requests_total",
        1,
        {
            "http.method": "GET",
            "http.route": "/health",
        },
    )
    client.send_histogram(
        "examples.request_latency_ms",
        143.2,
        {
            "http.method": "GET",
            "http.route": "/predict",
        },
    )
    client.send_gauge(
        "examples.cpu_utilization",
        37.5,
        {
            "host.name": "localhost",
        },
        unit="%",
    )

    # Logs
    client.send_log(
        "OTel educational example started.",
        severity="INFO",
        attributes={
            "component": "examples/otel_client_example.py",
            "event.type": "startup",
        },
    )
    client.send_log(
        "Simulated warning log to demonstrate severity handling.",
        severity="WARNING",
        attributes={
            "component": "examples/otel_client_example.py",
            "event.type": "warning",
        },
    )

    # Give exporters a moment to flush periodic batches.
    time.sleep(3)
    client.shutdown()
    print("Telemetry sent successfully.")


if __name__ == "__main__":
    main()
