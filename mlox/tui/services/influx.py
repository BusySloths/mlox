"""Safe, bounded status helpers for the InfluxDB TUI service view."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table


def influx_summary(service: Any, query_service: Any | None = None) -> dict[str, Any]:
    """Build display data without credentials, certificates, or raw queries."""
    destinations = getattr(service, "collector_destinations", lambda: {})()
    summary = {
        "name": str(getattr(service, "name", "InfluxDB 3 Core")),
        "state": str(getattr(service, "state", "unknown")),
        "url": str(getattr(service, "service_urls", {}).get("InfluxDB", "not deployed")),
        "database": str(getattr(service, "database", "telemetry")),
        "destinations": {key: bool(value) for key, value in destinations.items()},
        "limits": "Queries: 500 rows, 300 s window, 30 s request timeout",
    }
    if query_service is not None:
        try:
            stored = query_service.summary()
            summary["measurements"] = list(stored.get("measurements", []))[:100]
            summary["activity"] = dict(stored.get("activity", {}))
            summary["health"] = dict(stored.get("health", {}))
        except Exception:
            summary["measurements"] = []
            summary["activity"] = {}
            summary["health"] = {"status": "unavailable"}
    return summary


def influx_panel(service: Any, query_service: Any | None = None) -> Panel:
    """Render an intentionally non-interactive status panel for the TUI."""
    summary = influx_summary(service, query_service)
    table = Table(show_header=False, box=None)
    table.add_row("Health", summary["state"])
    table.add_row("Endpoint", summary["url"])
    table.add_row("Database", summary["database"])
    table.add_row("Operational limits", summary["limits"])
    if "measurements" in summary:
        table.add_row("Measurements", ", ".join(summary["measurements"]) or "none")
        activity = summary.get("activity", {})
        table.add_row("Recent activity", ", ".join(f"{k}: {v}" for k, v in activity.items()) or "none")
    return Panel(table, title="InfluxDB telemetry")
