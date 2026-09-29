"""Educational OTel client example; see examples/README.md for configuration.

What this demonstrates:
- Discover an OTEL collector service from your active MLOX infra
- Build an ``OTelClient`` from service secrets
- Emit spans, metrics, and logs in one short run

Requires MLOX_PROJECT_PATH and MLOX_PROJECT_PASSWORD. Missing optional
providers are reported; without telemetry, emission is skipped.
"""

from __future__ import annotations

import time
import logging

from examples.runtime import setup_runtime


def main() -> None:
    client, _ = setup_runtime()
    if client is None:
        print("No telemetry provider configured; telemetry emission skipped.")
        return
    try:
        emit_telemetry(client)
    finally:
        client.shutdown()


def emit_telemetry(client) -> None:

    # Traces: parent + nested span
    with client.span(
        "examples.otel.parent_span",
        attributes={
            "workflow.step": "start",
            "example": True,
        },
    ):
        time.sleep(0.45)
        with client.span(
            "examples.otel.nested_span",
            attributes={
                "workflow.step": "nested",
                "latency.bucket": "medium",
            },
        ) as nested_span:
            nested_start = time.perf_counter()
            time.sleep(0.1)
            nested_span.set_attribute(
                "example.measured_duration_ms",
                round((time.perf_counter() - nested_start) * 1000, 3),
            )
        time.sleep(0.45)

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

    print("Telemetry queued; exporters flush on shutdown. Check collector for delivery.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
