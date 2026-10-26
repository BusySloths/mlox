"""Backend-neutral, bounded telemetry query interface."""

from __future__ import annotations

from typing import Any, Protocol

import requests

from mlox.services.influx.client import InfluxClient


class TelemetryQueryService(Protocol):
    def recent_spans(self, *, since_seconds: int = 300, limit: int = 500) -> list[dict[str, Any]]: ...


class InfluxTelemetryQueryService:
    """Influx implementation with fixed server-side time, series, and row bounds."""

    def __init__(self, client: InfluxClient, *, max_rows: int = 500, timeout_seconds: int = 300):
        self.client = client
        self.max_rows = min(max(max_rows, 1), 1000)
        self.timeout_seconds = min(max(timeout_seconds, 1), 86_400)

    def recent_spans(self, *, since_seconds: int = 300, limit: int = 500) -> list[dict[str, Any]]:
        window = min(max(int(since_seconds), 1), self.timeout_seconds)
        rows = min(max(int(limit), 1), self.max_rows)
        # The collector's Influx exporter writes spans into this logical table.
        # This query is intentionally fixed: Operations never accepts raw SQL.
        return self.client.query(
            "SELECT * FROM spans WHERE time >= now() - INTERVAL "
            f"'{window} seconds' ORDER BY time ASC",
            max_rows=rows,
        )

    def summary(self) -> dict[str, Any]:
        """Return a bounded snapshot of stored metrics, spans, and logs."""
        errors: dict[str, str] = {}

        def load_signal(name: str, loader):
            try:
                return loader()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                table = getattr(exc, "influx_table", None)
                if status in {401, 403}:
                    errors[name] = f"InfluxDB rejected access (HTTP {status})."
                elif status == 400:
                    target = f" for table {table!r}" if table else ""
                    errors[name] = (
                        f"InfluxDB rejected the {name} query{target} (HTTP 400)."
                    )
                else:
                    errors[name] = f"InfluxDB {name} query failed (HTTP {status})."
                return []
            except Exception:
                errors[name] = f"Could not query recent {name}."
                return []

        measurements = load_signal(
            "measurements", lambda: self.client.measurements(max_rows=500)
        )
        metrics = load_signal(
            "metrics",
            lambda: self.client.recent_metrics(
                since_seconds=self.timeout_seconds,
                limit=min(self.max_rows, 100),
                measurement_names=measurements,
            ),
        )
        signal_row_limit = min(self.max_rows, 25)
        spans = load_signal(
            "spans",
            lambda: self.client.recent_spans(
                since_seconds=self.timeout_seconds,
                limit=signal_row_limit,
            ),
        )
        logs = load_signal(
            "logs",
            lambda: self.client.recent_logs(
                since_seconds=self.timeout_seconds,
                limit=signal_row_limit,
            ),
        )
        health = load_signal("health", self.client.health)
        return {
            "health": health if isinstance(health, dict) else {"status": "unknown"},
            "measurements": measurements,
            "activity": {
                "metrics": len(metrics),
                "spans": len(spans),
                "logs": len(logs),
            },
            "metrics": metrics,
            "spans": spans,
            "logs": logs,
            "errors": errors,
            "limits": {"rows": self.max_rows, "window_seconds": self.timeout_seconds},
        }
