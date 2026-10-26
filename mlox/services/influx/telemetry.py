"""Backend-neutral, bounded telemetry query interface."""

from __future__ import annotations

from typing import Any, Protocol

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
