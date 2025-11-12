"""Textual UI helpers for the OpenTelemetry collector service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

import pandas as pd
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Select, Sparkline, Static

from mlox.infra import Bundle, Infrastructure
from mlox.services.otel.docker import OtelDockerService
from mlox.services.otel.ui import (
    STANDARD_METRIC_GROUPS,
    _build_metric_frames,
    _extract_log_records,
    _extract_span_records,
    _load_jsonl,
    _split_telemetry_payload,
)

MAX_POINTS_PER_SERIES = 120


@dataclass
class MetricGroup:
    """Aggregated metric series representing a standard telemetry view."""

    key: str
    label: str
    timestamps: list[datetime]
    values: list[float]
    unit: str | None = None

    def latest_value(self) -> float | None:
        return self.values[-1] if self.values else None

    def latest_timestamp(self) -> datetime | None:
        return self.timestamps[-1] if self.timestamps else None


@dataclass
class TelemetrySnapshot:
    """Structured representation of collector telemetry for the TUI."""

    summary: Dict[str, int]
    groups: Dict[str, MetricGroup]
    messages: list[str]
    errors: int = 0


def _slugify(label: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_") or label.lower()


def _aggregate_standard_groups(numeric_df: pd.DataFrame) -> Dict[str, MetricGroup]:
    if numeric_df.empty:
        return {}

    normalized = numeric_df.dropna(subset=["timestamp", "value"]).copy()
    if normalized.empty:
        return {}

    normalized.sort_values("timestamp", inplace=True)

    groups: Dict[str, MetricGroup] = {}
    for label, keywords in STANDARD_METRIC_GROUPS.items():
        if not keywords:
            continue
        mask = normalized["name"].str.contains("|".join(keywords), case=False, na=False)
        group_df = normalized.loc[mask]
        if group_df.empty:
            continue
        aggregated = (
            group_df.groupby("timestamp", as_index=False)["value"].mean().sort_values("timestamp")
        )
        if aggregated.empty:
            continue
        unit_series = group_df["unit"].dropna()
        unit = str(unit_series.iloc[0]) if not unit_series.empty else None
        timestamps = [ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts for ts in aggregated["timestamp"]]
        values = aggregated["value"].astype(float).tolist()
        if len(values) > MAX_POINTS_PER_SERIES:
            values = values[-MAX_POINTS_PER_SERIES:]
            timestamps = timestamps[-MAX_POINTS_PER_SERIES:]
        key = _slugify(label)
        groups[key] = MetricGroup(
            key=key,
            label=label,
            timestamps=timestamps,
            values=values,
            unit=unit,
        )
    return groups


def _build_snapshot(telemetry_raw: str | None) -> TelemetrySnapshot:
    telemetry_data, errors = _load_jsonl(telemetry_raw)

    summary = {"spans": 0, "logs": 0, "metric_points": 0}
    if not telemetry_data:
        messages = [
            "No telemetry data loaded yet. Trigger collector traffic to populate metrics."
        ]
        if errors:
            messages.append(f"Skipped {errors} malformed telemetry records during parsing.")
        return TelemetrySnapshot(summary=summary, groups={}, messages=messages, errors=errors)

    span_payloads, log_payloads, metric_payloads = _split_telemetry_payload(telemetry_data)

    span_records = _extract_span_records(span_payloads)
    log_records = _extract_log_records(log_payloads)
    _, numeric_df = _build_metric_frames(metric_payloads)

    summary = {
        "spans": len(span_records),
        "logs": len(log_records),
        "metric_points": len(numeric_df),
    }

    groups = _aggregate_standard_groups(numeric_df)

    messages: list[str] = []
    if errors:
        messages.append(f"Skipped {errors} malformed telemetry records during parsing.")
    if not groups:
        messages.append(
            "Standard CPU, memory, or network metrics were not detected in the telemetry stream."
        )

    return TelemetrySnapshot(summary=summary, groups=groups, messages=messages, errors=errors)


class OtelTelemetryPanel(VerticalScroll):
    """Container rendering OTEL telemetry with sparkline visualisations."""

    selected_key: reactive[str | None] = reactive(None)

    def __init__(self, snapshot: TelemetrySnapshot) -> None:
        super().__init__(id="otel-telemetry-panel")
        self.snapshot = snapshot

    def compose(self) -> ComposeResult:
        yield Static("", id="otel-telemetry-status")
        yield Static("", id="otel-telemetry-summary")
        with Horizontal(id="otel-telemetry-controls"):
            yield Select(options=[], prompt="Metric Group", id="otel-telemetry-select")
        yield Sparkline([], id="otel-telemetry-sparkline", summary="Metric trend")
        yield Static("", id="otel-telemetry-details")

    @property
    def status(self) -> Static:
        return self.query_one("#otel-telemetry-status", Static)

    @property
    def summary_view(self) -> Static:
        return self.query_one("#otel-telemetry-summary", Static)

    @property
    def metric_select(self) -> Select:
        return self.query_one("#otel-telemetry-select", Select)

    @property
    def sparkline(self) -> Sparkline:
        return self.query_one("#otel-telemetry-sparkline", Sparkline)

    @property
    def details(self) -> Static:
        return self.query_one("#otel-telemetry-details", Static)

    def on_mount(self) -> None:
        self._populate_summary()
        self._populate_controls()

    def _populate_summary(self) -> None:
        table = Table.grid(padding=(0, 1))
        table.add_column("Metric", style="cyan", justify="right")
        table.add_column("Value", justify="left")
        for key, value in self.snapshot.summary.items():
            label = key.replace("_", " ").title()
            table.add_row(label, f"{value}")
        panel = Panel(table, title="Telemetry Summary", border_style="green")
        self.summary_view.update(panel)

    def _populate_controls(self) -> None:
        messages = list(self.snapshot.messages)
        if self.snapshot.groups:
            options = [
                (group.label, key)
                for key, group in self.snapshot.groups.items()
                if isinstance(group, MetricGroup)
            ]
            self.metric_select.set_options(options)
            self.selected_key = options[0][1]
            self.metric_select.value = self.selected_key
            status_text = "\n".join(messages) if messages else "Telemetry loaded successfully."
            self.status.update(status_text)
            self._update_metric_view(self.selected_key)
        else:
            self.metric_select.set_options([])
            self.metric_select.value = None
            self.sparkline.data = []
            self.sparkline.summary = "Metric trend"
            info = Text(
                "No standard CPU, memory, or network metrics are available for the collector yet."
            )
            self.details.update(Panel(info, border_style="yellow"))
            if not messages:
                messages.append(
                    "Collect CPU, memory, or network metrics to populate this view."
                )
            self.status.update("\n".join(messages))

    def _update_metric_view(self, key: str | None) -> None:
        if not key:
            self.sparkline.data = []
            self.sparkline.summary = "Metric trend"
            self.details.update("")
            return

        group = self.snapshot.groups.get(key)
        if not isinstance(group, MetricGroup) or not group.values:
            self.sparkline.data = []
            self.sparkline.summary = "Metric trend"
            info = Text("Selected metric group has no datapoints yet.")
            self.details.update(Panel(info, border_style="yellow"))
            return

        self.sparkline.data = group.values
        self.sparkline.summary = f"{group.label} trend"
        latest = group.latest_value()
        timestamp = group.latest_timestamp()
        unit = group.unit or ""
        if latest is not None:
            latest_text = f"{latest:,.2f}{unit}" if unit else f"{latest:,.2f}"
        else:
            latest_text = "N/A"
        ts_text = timestamp.isoformat(sep=" ") if timestamp else "Unknown time"

        detail_table = Table.grid(padding=(0, 1))
        detail_table.add_column(justify="right", style="cyan")
        detail_table.add_column(justify="left")
        detail_table.add_row("Latest", latest_text)
        detail_table.add_row("Timestamp", ts_text)
        if unit:
            detail_table.add_row("Unit", unit)
        self.details.update(Panel(detail_table, title=group.label, border_style="blue"))

    @on(Select.Changed, "#otel-telemetry-select")
    def handle_metric_changed(self, event: Select.Changed) -> None:  # pragma: no cover - UI callback
        self.selected_key = event.value
        self._update_metric_view(event.value)


def tui_settings(
    infra: Infrastructure,
    bundle: Bundle,
    service: OtelDockerService,
) -> OtelTelemetryPanel:
    """Return a Textual container visualising OTEL telemetry."""

    telemetry_raw = service.get_telemetry_data(bundle)
    snapshot = _build_snapshot(telemetry_raw)
    return OtelTelemetryPanel(snapshot)
