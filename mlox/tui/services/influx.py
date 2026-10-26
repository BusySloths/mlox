"""Safe, bounded status helpers for the InfluxDB TUI service view."""

from __future__ import annotations

from typing import Any
import json
import requests

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.containers import Vertical
from textual.widgets import Button, Select, Static, TabbedContent, TabPane

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
            summary["metrics"] = list(stored.get("metrics", []))
            summary["spans"] = list(stored.get("spans", []))
            summary["logs"] = list(stored.get("logs", []))
            summary["health"] = dict(stored.get("health", {}))
            summary["errors"] = dict(stored.get("errors", {}))
            if summary["errors"]:
                summary["error"] = " ".join(summary["errors"].values())
        except Exception as exc:
            summary["measurements"] = []
            summary["activity"] = {}
            summary["metrics"] = []
            summary["spans"] = []
            summary["logs"] = []
            summary["errors"] = {}
            summary["health"] = {"status": "unavailable"}
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                status = exc.response.status_code
                summary["error"] = (
                    f"InfluxDB rejected the data query (HTTP {status})."
                    if status == 400
                    else f"InfluxDB rejected access (HTTP {status})."
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


def _signal_table(
    title: str,
    rows: list[dict[str, Any]],
    preferred_columns: tuple[str, ...],
) -> Panel:
    """Render a compact, bounded signal table without interpreting markup."""
    table = Table(show_header=True, expand=True, row_styles=("", "dim"))
    if not rows:
        table.add_column("Data", overflow="fold")
        table.add_row("No recent data")
        return Panel(table, title=f"{title} · 0 rows")

    available = {str(key) for row in rows for key in row}
    columns = [key for key in preferred_columns if key in available]
    columns.extend(sorted(available - set(columns)))
    columns = columns[:7]
    for column in columns:
        table.add_column(column, overflow="fold", max_width=42)
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column, "")
            if isinstance(value, (dict, list, tuple)):
                rendered = json.dumps(value, ensure_ascii=False, default=str)
            else:
                rendered = str(value)
            if len(rendered) > 240:
                rendered = rendered[:237] + "…"
            values.append(Text(rendered))
        table.add_row(*values)
    return Panel(table, title=f"{title} · {len(rows)} rows")


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
        self._metric_rows: list[dict[str, Any]] = []
        self._trace_rows: list[dict[str, Any]] = []
        self._log_rows: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Button("Refresh", id="influx-refresh", variant="primary")
        with TabbedContent(id="influx-data-tabs"):
            with TabPane("Metrics", id="influx-metrics-tab"):
                yield Select(
                    [],
                    prompt="Select a metric measurement",
                    allow_blank=True,
                    id="influx-metric-select",
                )
                yield Static("Loading metrics…", id="influx-metrics")
            with TabPane("Traces", id="influx-traces-tab"):
                yield Select(
                    [("All services", "*")],
                    value="*",
                    id="influx-trace-service-select",
                )
                yield Static("Loading traces…", id="influx-spans")
            with TabPane("Logs", id="influx-logs-tab"):
                yield Select(
                    [("All services", "*")],
                    value="*",
                    id="influx-log-service-select",
                )
                yield Static("Loading logs…", id="influx-logs")
        yield Static("", id="influx-message")

    def on_mount(self) -> None:
        self._refresh()

    @on(Button.Pressed, "#influx-refresh")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self._refresh()

    @on(Select.Changed, "#influx-metric-select")
    def handle_metric_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            self._render_metric_table(None)
        else:
            self._render_metric_table(str(event.value))

    @on(Select.Changed, "#influx-trace-service-select")
    def handle_trace_service_changed(self, event: Select.Changed) -> None:
        self._render_trace_table(str(event.value))

    @on(Select.Changed, "#influx-log-service-select")
    def handle_log_service_changed(self, event: Select.Changed) -> None:
        self._render_log_table(str(event.value))

    def _refresh(self) -> None:
        if not self._widgets_available():
            return
        connection = getattr(self.service, "service_urls", {}).get("InfluxDB")
        if not connection or getattr(self.service, "state", "") != "running":
            summary = influx_summary(self.service)
            self._apply_summary(
                summary,
                "InfluxDB is not deployed yet. Run Setup Service to initialize it.",
            )
            return
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
        if not self._widgets_available():
            return
        button = self.query_one("#influx-refresh", Button)
        button.disabled = False
        button.label = "Refresh"
        health = summary.get("health", {})
        metrics = summary.get("metrics", [])
        spans = summary.get("spans", [])
        logs = summary.get("logs", [])
        self._metric_rows = metrics
        metric_names = list(
            dict.fromkeys(
                str(row["measurement"])
                for row in metrics
                if row.get("measurement")
            )
        )
        metric_select = self.query_one("#influx-metric-select", Select)
        current_metric = metric_select.value
        metric_select.set_options([(name, name) for name in metric_names])
        metric_select.disabled = not metric_names
        if metric_names:
            selected_metric = (
                str(current_metric)
                if current_metric in metric_names
                else metric_names[0]
            )
            metric_select.value = selected_metric
            self._render_metric_table(selected_metric)
        else:
            metric_select.clear()
            self._render_metric_table(None)
        self._trace_rows = spans
        self._log_rows = logs
        self._set_service_options("#influx-trace-service-select", spans)
        self._set_service_options("#influx-log-service-select", logs)
        self._render_trace_table(self._selected_service("#influx-trace-service-select"))
        self._render_log_table(self._selected_service("#influx-log-service-select"))
        message_text = message
        if health.get("status") and message == "InfluxDB data refreshed.":
            counts = summary.get("activity", {})
            message_text = (
                f"{health.get('status')} · {summary.get('database', 'telemetry')} · "
                f"metrics {counts.get('metrics', 0)}, spans {counts.get('spans', 0)}, "
                f"logs {counts.get('logs', 0)}"
            )
        self.query_one("#influx-message", Static).update(message_text)

    def _render_metric_table(self, measurement: str | None) -> None:
        if not self._widgets_available():
            return
        rows = (
            [
                row
                for row in self._metric_rows
                if row.get("measurement") == measurement
            ]
            if measurement
            else []
        )
        title = f"Metric · {measurement}" if measurement else "Metric"
        self.query_one("#influx-metrics", Static).update(
            _signal_table(
                title,
                rows,
                ("time", "service.name", "name", "value", "counter", "gauge"),
            )
        )

    def _set_service_options(
        self, select_id: str, rows: list[dict[str, Any]]
    ) -> None:
        select = self.query_one(select_id, Select)
        current = self._selected_service(select_id)
        names = sorted(
            {
                str(row["service.name"])
                for row in rows
                if row.get("service.name")
            }
        )
        options = [("All services", "*")] + [(name, name) for name in names]
        select.set_options(options)
        select.value = current if current == "*" or current in names else "*"

    def _selected_service(self, select_id: str) -> str:
        value = self.query_one(select_id, Select).value
        return "*" if value is Select.BLANK else str(value)

    def _render_trace_table(self, service_name: str) -> None:
        if not self._widgets_available():
            return
        rows = self._filter_service(self._trace_rows, service_name)
        title = "Traces" if service_name == "*" else f"Traces · {service_name}"
        self.query_one("#influx-spans", Static).update(
            _signal_table(
                title,
                rows,
                (
                    "time",
                    "name",
                    "service.name",
                    "mlox.pipeline.name",
                    "mlox.step.path",
                    "mlox.model.name",
                    "trace_id",
                ),
            )
        )

    def _render_log_table(self, service_name: str) -> None:
        if not self._widgets_available():
            return
        rows = self._filter_service(self._log_rows, service_name)
        title = "Logs" if service_name == "*" else f"Logs · {service_name}"
        self.query_one("#influx-logs", Static).update(
            _signal_table(
                title,
                rows,
                ("time", "severity_text", "service.name", "body", "trace_id"),
            )
        )

    @staticmethod
    def _filter_service(
        rows: list[dict[str, Any]], service_name: str
    ) -> list[dict[str, Any]]:
        if service_name == "*":
            return rows
        return [row for row in rows if row.get("service.name") == service_name]

    def _widgets_available(self) -> bool:
        """An attached panel may already be composing or detaching its children."""

        try:
            self.query_one("#influx-refresh", Button)
            self.query_one("#influx-metric-select", Select)
            self.query_one("#influx-trace-service-select", Select)
            self.query_one("#influx-log-service-select", Select)
            self.query_one("#influx-metrics", Static)
            self.query_one("#influx-spans", Static)
            self.query_one("#influx-logs", Static)
            self.query_one("#influx-message", Static)
        except NoMatches:
            return False
        return True


def settings(
    infra: Infrastructure,
    bundle: Bundle,
    service: Any,
) -> InfluxSettingsPanel:
    """Return the dedicated InfluxDB TUI service tab."""

    return InfluxSettingsPanel(infra, bundle, service)
