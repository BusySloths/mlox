"""Textual UI helpers for the OpenTelemetry collector service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Dict

import pandas as pd
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
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
SPARKLINE_COLORS = (
    ("#55efc4", "#00b894"),
    ("#fab1a0", "#e17055"),
    ("#74b9ff", "#0984e3"),
)


@dataclass
class MetricSeries:
    """Single metric series inside a telemetry group (e.g. 5 min average)."""

    key: str
    label: str
    timestamps: list[datetime]
    values: list[float]
    unit: str | None = None
    resolution: str | None = None

    def latest_value(self) -> float | None:
        return self.values[-1] if self.values else None

    def latest_timestamp(self) -> datetime | None:
        return self.timestamps[-1] if self.timestamps else None

    def start_timestamp(self) -> datetime | None:
        return self.timestamps[0] if self.timestamps else None

    def end_timestamp(self) -> datetime | None:
        return self.timestamps[-1] if self.timestamps else None


@dataclass
class MetricGroup:
    """Aggregated metric series representing a standard telemetry view."""

    key: str
    label: str
    series: list[MetricSeries]

    def has_data(self) -> bool:
        return any(series.values for series in self.series)


@dataclass
class TelemetrySnapshot:
    """Structured representation of collector telemetry for the TUI."""

    summary: Dict[str, int]
    groups: Dict[str, MetricGroup]
    messages: list[str]
    errors: int = 0


def _slugify(label: str) -> str:
    return (
        "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
        or label.lower()
    )


def _ts_display(ts: datetime | None) -> str:
    return ts.isoformat(sep=" ") if ts else "Unknown time"


RESOLUTION_HINTS: dict[str, tuple[str, ...]] = {
    "1m": ("1m", "1_min", "1-minute", "1min", ".1"),
    "5m": ("5m", "5_min", "5-minute", "5min", ".5"),
    "10m": ("10m", "10_min", "10-minute", "10min", ".10"),
    "15m": ("15m", "15_min", "15-minute", "15min", ".15"),
}
RESOLUTION_LABELS = {
    "1m": "1 min avg",
    "5m": "5 min avg",
    "10m": "10 min avg",
    "15m": "15 min avg",
}
RESOLUTION_PRIORITY = {"1m": 0, "5m": 1, "10m": 2, "15m": 3}


def _detect_resolution(metric_name: str) -> tuple[str, str]:
    normalized = metric_name.lower()
    for resolution, hints in RESOLUTION_HINTS.items():
        if any(h in normalized for h in hints):
            return resolution, RESOLUTION_LABELS.get(resolution, f"{resolution} avg")

    minutes_match = re.search(r"(\d+)\s*(?:m|min|minute)", normalized)
    if minutes_match:
        minutes = minutes_match.group(1)
        key = f"{minutes}m"
        return key, f"{minutes} min avg"

    trailing_match = re.search(r"(?:^|[._-])(\d{1,2})(?:$|[._-])", normalized)
    if trailing_match:
        minutes = trailing_match.group(1)
        key = f"{minutes}m"
        return key, f"{minutes} min avg"

    return "instant", "Instant sample"


def _sort_series(series: MetricSeries) -> tuple[int, str]:
    priority = RESOLUTION_PRIORITY.get(series.resolution or "", 50)
    return (priority, series.label)


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
        series_list: list[MetricSeries] = []
        for metric_name, metric_df in group_df.groupby("name"):
            aggregated = (
                metric_df.groupby("timestamp", as_index=False)["value"]
                .mean()
                .sort_values("timestamp")
            )
            if aggregated.empty:
                continue
            unit_series = metric_df["unit"].dropna()
            unit = str(unit_series.iloc[0]) if not unit_series.empty else None
            timestamps = [
                ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                for ts in aggregated["timestamp"]
            ]
            values = aggregated["value"].astype(float).tolist()
            if len(values) > MAX_POINTS_PER_SERIES:
                values = values[-MAX_POINTS_PER_SERIES:]
                timestamps = timestamps[-MAX_POINTS_PER_SERIES:]
            resolution_key, resolution_label = _detect_resolution(metric_name)
            series_key = _slugify(f"{label}_{metric_name}")
            series_list.append(
                MetricSeries(
                    key=series_key,
                    label=resolution_label,
                    timestamps=timestamps,
                    values=values,
                    unit=unit,
                    resolution=resolution_key,
                )
            )
        if not series_list:
            continue
        key = _slugify(label)
        groups[key] = MetricGroup(
            key=key,
            label=label,
            series=sorted(series_list, key=_sort_series),
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
            messages.append(
                f"Skipped {errors} malformed telemetry records during parsing."
            )
        return TelemetrySnapshot(
            summary=summary, groups={}, messages=messages, errors=errors
        )

    span_payloads, log_payloads, metric_payloads = _split_telemetry_payload(
        telemetry_data
    )

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

    return TelemetrySnapshot(
        summary=summary, groups=groups, messages=messages, errors=errors
    )


class OtelTelemetryPanel(VerticalScroll):
    """Container rendering OTEL telemetry with sparkline visualisations."""

    selected_key: reactive[str | None] = reactive(None)

    def __init__(self, snapshot: TelemetrySnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot

    def compose(self) -> ComposeResult:
        yield Static("", id="otel-telemetry-status")
        yield Static("", id="otel-telemetry-summary")
        with Horizontal(id="otel-telemetry-controls"):
            yield Select(options=[], prompt="Metric Group", id="otel-telemetry-select")
        with Vertical(id="otel-telemetry-sparklines"):
            for idx, (min_color, max_color) in enumerate(SPARKLINE_COLORS):
                with Vertical(
                    id=f"otel-telemetry-sparkline-slot-{idx}",
                    classes="otel-telemetry-sparkline-slot",
                ):
                    yield Static("", id=f"otel-telemetry-sparkline-label-{idx}")
                    yield Sparkline(
                        [],
                        id=f"otel-telemetry-sparkline-{idx}",
                        min_color=min_color,
                        max_color=max_color,
                    )
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
    def details(self) -> Static:
        return self.query_one("#otel-telemetry-details", Static)

    def _sparkline_widgets(self) -> list[tuple[Static, Sparkline]]:
        widgets: list[tuple[Static, Sparkline]] = []
        for idx in range(len(SPARKLINE_COLORS)):
            label_view = self.query_one(
                f"#otel-telemetry-sparkline-label-{idx}", Static
            )
            sparkline = self.query_one(f"#otel-telemetry-sparkline-{idx}", Sparkline)
            widgets.append((label_view, sparkline))
        return widgets

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
            status_text = (
                "\n".join(messages) if messages else "Telemetry loaded successfully."
            )
            self.status.update(status_text)
            self._update_metric_view(self.selected_key)
        else:
            self.metric_select.set_options([])
            self.metric_select.value = None
            for label_view, sparkline in self._sparkline_widgets():
                label_view.update("No data")
                sparkline.data = []
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
        slots = self._sparkline_widgets()
        for label_view, sparkline in slots:
            label_view.update("No data")
            sparkline.data = []

        if not key:
            self.details.update("")
            return

        group = self.snapshot.groups.get(key)
        if not isinstance(group, MetricGroup) or not group.has_data():
            info = Text("Selected metric group has no datapoints yet.")
            self.details.update(Panel(info, border_style="yellow"))
            return

        detail_table = Table.grid(padding=(0, 1))
        detail_table.add_column("Series", style="cyan", justify="left")
        detail_table.add_column("Latest", justify="right")
        detail_table.add_column("Start", justify="left")
        detail_table.add_column("End", justify="left")
        detail_table.add_column("Unit", justify="left")

        for (label_view, sparkline), series in zip(slots, group.series):
            label_view.update(series.label)
            sparkline.data = series.values
            latest = series.latest_value()
            latest_text = f"{latest:,.2f}" if latest is not None else "N/A"
            if series.unit:
                latest_text = f"{latest_text}{series.unit}"
            detail_table.add_row(
                series.label,
                latest_text,
                _ts_display(series.start_timestamp()),
                _ts_display(series.end_timestamp()),
                series.unit or "-",
            )

        self.details.update(
            Panel(
                detail_table,
                title=f"{group.label} trends",
                border_style="blue",
            )
        )

    @on(Select.Changed, "#otel-telemetry-select")
    def handle_metric_changed(
        self, event: Select.Changed
    ) -> None:  # pragma: no cover - UI callback
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
