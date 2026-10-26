"""Safe, bounded status helpers for the InfluxDB TUI service view."""

from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table


def influx_summary(service: Any) -> dict[str, Any]:
    """Build display data without credentials, certificates, or raw queries."""
    destinations = getattr(service, "collector_destinations", lambda: {})()
    return {
        "name": str(getattr(service, "name", "InfluxDB 3 Core")),
        "state": str(getattr(service, "state", "unknown")),
        "url": str(getattr(service, "service_urls", {}).get("InfluxDB", "not deployed")),
        "database": str(getattr(service, "database", "telemetry")),
        "destinations": {key: bool(value) for key, value in destinations.items()},
        "limits": "Queries: 500 rows, 300 s window, 30 s request timeout",
    }


def influx_panel(service: Any) -> Panel:
    """Render an intentionally non-interactive status panel for the TUI."""
    summary = influx_summary(service)
    table = Table(show_header=False, box=None)
    table.add_row("Health", summary["state"])
    table.add_row("Endpoint", summary["url"])
    table.add_row("Database", summary["database"])
    table.add_row("Operational limits", summary["limits"])
    return Panel(table, title="InfluxDB telemetry")
