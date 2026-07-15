from __future__ import annotations

from typing import Any

from rich.panel import Panel
from rich.table import Table
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Button, DataTable, Static, TabbedContent, TabPane

from mlox.application.result import OperationResult
from mlox.application.use_cases.mlflow_gateway import (
    clear_gateway_cache,
    describe_gateway,
)
from mlox.infra import Bundle, Infrastructure


class MLflowGatewaySettingsPanel(Vertical):
    """Models, cache state, and metrics for one MLflow Gateway service."""

    def __init__(self, infra: Infrastructure, bundle: Bundle, service: Any) -> None:
        super().__init__()
        self.infra = infra
        self.bundle = bundle
        self.service = service

    def compose(self) -> ComposeResult:
        with Horizontal(id="mlflow-gateway-actions"):
            yield Button("Refresh", id="mlflow-gateway-refresh", variant="primary")
            yield Button(
                "Clear Model Cache", id="mlflow-gateway-clear-cache", variant="warning"
            )
        yield Static("Loading MLflow Gateway settings...", id="mlflow-gateway-status")
        yield Static("", id="mlflow-gateway-summary")
        with TabbedContent(id="mlflow-gateway-content-tabs"):
            with TabPane("Models", id="mlflow-gateway-models-tab"):
                yield Static(
                    "Models available through the linked MLflow registry.",
                    classes="mlflow-gateway-tab-help",
                )
                models = DataTable(id="mlflow-gateway-models")
                models.add_columns("Model", "Version", "Stage", "Description")
                yield models
            with TabPane("Model Cache", id="mlflow-gateway-cache-tab"):
                yield Static(
                    "Models currently loaded in this gateway process.",
                    classes="mlflow-gateway-tab-help",
                )
                cache = DataTable(id="mlflow-gateway-cache")
                cache.add_columns(
                    "Model URI", "Calls", "Loaded", "Last Call", "Idle Days"
                )
                yield cache
            with TabPane("Metrics", id="mlflow-gateway-metrics-tab"):
                yield Static(
                    "Key Prometheus samples. Histogram buckets and generated "
                    "timestamps are hidden.",
                    classes="mlflow-gateway-tab-help",
                )
                metrics = DataTable(id="mlflow-gateway-metrics")
                metrics.add_columns("Metric", "Labels", "Value")
                yield metrics

    def on_mount(self) -> None:
        self.refresh_data()

    @on(Button.Pressed, "#mlflow-gateway-refresh")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.refresh_data()

    @on(Button.Pressed, "#mlflow-gateway-clear-cache")
    def handle_clear_cache(self, _: Button.Pressed) -> None:
        self._set_busy(True)
        app = self.app

        def clear() -> None:
            result = clear_gateway_cache(self.service)
            app.call_from_thread(self._after_clear, result)

        app.run_worker(
            clear, thread=True, exclusive=True, group=f"mlflow-gateway-clear-{id(self)}"
        )

    def refresh_data(self) -> None:
        self._set_busy(True)
        try:
            self.query_one("#mlflow-gateway-status", Static).update(
                "Loading MLflow Gateway settings..."
            )
        except NoMatches:
            return

        app = self.app

        def load() -> None:
            result = describe_gateway(self.service)
            app.call_from_thread(self._apply_result, result)

        app.run_worker(
            load, thread=True, exclusive=True, group=f"mlflow-gateway-load-{id(self)}"
        )

    def _after_clear(self, result: OperationResult) -> None:
        if not self.is_attached:
            return
        try:
            self.notify(
                result.message,
                severity="information" if result.success else "error",
            )
        except NoMatches:
            return
        self.refresh_data()

    def _apply_result(self, result: OperationResult) -> None:
        if not self.is_attached:
            return
        try:
            status = self.query_one("#mlflow-gateway-status", Static)
        except NoMatches:
            return
        self._set_busy(False)
        status.update(result.message)
        if not result.success or not result.data:
            return
        self._populate_summary(result.data.get("summary", {}))
        self._populate_models_table(result.data.get("models", []))
        self._populate_cache_table(result.data.get("cache", {}))
        self._populate_metrics_table(result.data.get("metrics", []))

    def _populate_summary(self, summary: dict[str, Any]) -> None:
        table = Table.grid(expand=True)
        for _ in range(6):
            table.add_column(justify="center")
        table.add_row(
            self._value("Requests", summary.get("requests")),
            self._value("Predictions", summary.get("predictions")),
            self._value("Errors", summary.get("prediction_errors")),
            self._value("Cache hits", summary.get("cache_hits")),
            self._value("Cache misses", summary.get("cache_misses")),
            self._value("Cached models", summary.get("cached_models")),
        )
        self.query_one("#mlflow-gateway-summary", Static).update(
            Panel(table, title="Gateway Overview", border_style="cyan")
        )

    def _populate_models_table(self, rows: list[dict[str, Any]]) -> None:
        table = self.query_one("#mlflow-gateway-models", DataTable)
        table.clear()
        for row in rows:
            table.add_row(
                str(row.get("Model", row.get("name", "-"))),
                str(row.get("Version", row.get("version", "-"))),
                str(row.get("Stage", row.get("status", "-"))),
                str(row.get("Description", row.get("description", ""))),
            )

    def _populate_cache_table(self, cache: dict[str, Any]) -> None:
        table = self.query_one("#mlflow-gateway-cache", DataTable)
        table.clear()
        for row in cache.get("cached_models", []) or []:
            table.add_row(
                str(row.get("model_uri", "-")),
                str(row.get("num_calls", 0)),
                str(row.get("loaded_at", "-")),
                str(row.get("last_call", "-")),
                f"{float(row.get('idle_days', 0)):.2f}",
            )

    def _populate_metrics_table(self, rows: list[dict[str, Any]]) -> None:
        table = self.query_one("#mlflow-gateway-metrics", DataTable)
        table.clear()
        for row in rows:
            name = str(row.get("name", ""))
            if name.endswith(("_bucket", "_created")):
                continue
            labels = ", ".join(
                f"{key}={value}" for key, value in row.get("labels", {}).items()
            )
            table.add_row(name or "-", labels or "-", f"{row.get('value', 0):g}")

    def _set_busy(self, busy: bool) -> None:
        for button in self.query(Button):
            button.disabled = busy

    @staticmethod
    def _value(label: str, value: Any) -> str:
        numeric = float(value or 0)
        shown = str(int(numeric)) if numeric.is_integer() else f"{numeric:.2f}"
        return f"[bold]{shown}[/bold]\n{label}"


def settings(
    infra: Infrastructure, bundle: Bundle, service: Any
) -> MLflowGatewaySettingsPanel:
    return MLflowGatewaySettingsPanel(infra, bundle, service)
