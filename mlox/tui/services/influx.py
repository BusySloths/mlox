"""Safe, bounded status helpers for the InfluxDB TUI service view."""

from __future__ import annotations

from typing import Any
import requests

from rich.panel import Panel
from rich.table import Table
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from mlox.infra import Bundle, Infrastructure


def influx_summary(service: Any, query_service: Any | None = None) -> dict[str, Any]:
    """Build display data without credentials, certificates, or raw queries."""
    destinations = getattr(service, "collector_destinations", lambda: {})()
    summary = {
        "name": str(getattr(service, "name", "InfluxDB 3 Core")),
        "state": str(getattr(service, "state", "unknown")),
        "url": str(
            getattr(service, "service_urls", {}).get("InfluxDB", "not deployed")
        ),
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
        except Exception as exc:
            summary["measurements"] = []
            summary["activity"] = {}
            summary["health"] = {"status": "unavailable"}
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                summary["error"] = (
                    f"InfluxDB rejected the data request (HTTP {exc.response.status_code}). "
                    "Container running does not confirm API authentication."
                )
            else:
                summary["error"] = "Could not query InfluxDB data."
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
        table.add_row(
            "Recent activity",
            ", ".join(f"{k}: {v}" for k, v in activity.items()) or "none",
        )
    return Panel(table, title="InfluxDB telemetry")


class InfluxSettingsPanel(Vertical):
    """Read-only, bounded InfluxDB data and statistics view for the TUI."""

    def __init__(
        self,
        infra: Infrastructure | None,
        bundle: Bundle | None,
        service: Any,
    ) -> None:
        super().__init__()
        self.infra = infra
        self.bundle = bundle
        self.service = service

    def compose(self) -> ComposeResult:
        with Horizontal(id="influx-toolbar"):
            yield Button("Refresh Data & Stats", id="influx-refresh", variant="primary")
            yield Static("Read-only bounded queries", id="influx-readonly-label")
        yield Static("Loading InfluxDB data…", id="influx-summary")
        yield Static("", id="influx-message")

    def on_mount(self) -> None:
        self._refresh()

    @on(Button.Pressed, "#influx-refresh")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self._refresh()

    def _refresh(self) -> None:
        button = self.query_one("#influx-refresh", Button)
        button.disabled = True
        button.label = "Loading…"
        app = self.app

        def load() -> None:
            try:
                backend = self.service.get_telemetry_query_service()
                summary = influx_summary(self.service, backend)
                message = summary.get("error", "InfluxDB data refreshed.")
            except Exception as exc:  # pragma: no cover - remote IO defensive path
                summary = influx_summary(self.service)
                message = f"Could not load InfluxDB data: {exc}"
            app.call_from_thread(self._apply_summary, summary, message)

        app.run_worker(
            load,
            thread=True,
            exclusive=True,
            group=f"influx-summary-{id(self)}",
        )

    def _apply_summary(self, summary: dict[str, Any], message: str) -> None:
        if not self.is_attached:
            return
        button = self.query_one("#influx-refresh", Button)
        button.disabled = False
        button.label = "Refresh Data & Stats"
        health = summary.get("health", {})
        measurements = ", ".join(summary.get("measurements", [])) or "none"
        activity = ", ".join(
            f"{name}: {value}" for name, value in summary.get("activity", {}).items()
        ) or "none"
        table = Table(show_header=False, box=None)
        table.add_row("Service state", str(summary.get("state", "unknown")))
        table.add_row("Health", str(health.get("status", "unknown")))
        table.add_row("Endpoint", str(summary.get("url", "not deployed")))
        table.add_row("Database", str(summary.get("database", "telemetry")))
        table.add_row("Measurements", measurements)
        table.add_row("Recent activity", activity)
        table.add_row("Query limits", str(summary.get("limits", "")))
        self.query_one("#influx-summary", Static).update(
            Panel(table, title="InfluxDB telemetry")
        )
        self.query_one("#influx-message", Static).update(message)


def settings(
    infra: Infrastructure,
    bundle: Bundle,
    service: Any,
) -> InfluxSettingsPanel:
    """Return the dedicated InfluxDB TUI service tab."""

    return InfluxSettingsPanel(infra, bundle, service)
