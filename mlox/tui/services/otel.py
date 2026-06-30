"""Textual UI helpers for the OpenTelemetry collector service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
from typing import Any, Dict

import pandas as pd
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static

from mlox.infra import Bundle, Infrastructure
from mlox.services.otel.docker import OtelDockerService
from mlox.view.services.otel import (
    STANDARD_METRIC_GROUPS,
    _build_metric_frames,
    _extract_log_records,
    _extract_span_records,
    _load_jsonl,
    _split_telemetry_payload,
)

MAX_POINTS_PER_SERIES = 120


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


@dataclass
class UsagePair:
    """Used/free resource values."""

    used: float | None = None
    free: float | None = None
    total_value: float | None = None
    unit: str | None = None
    history: list[float] | None = None
    scope: str | None = None

    @property
    def total(self) -> float | None:
        if self.total_value is not None:
            return self.total_value
        if self.used is None or self.free is None:
            return None
        return self.used + self.free

    @property
    def used_ratio(self) -> float | None:
        total = self.total
        if total is None or total <= 0 or self.used is None:
            return None
        return self.used / total


@dataclass
class CpuUsage:
    """CPU utilization snapshot."""

    now_used_ratio: float | None = None
    now_free_ratio: float | None = None
    five_min_used_ratio: float | None = None
    five_min_free_ratio: float | None = None
    history: list[float] | None = None
    source: str | None = None
    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None
    logical_cpus: int | None = None


@dataclass
class NetworkUsage:
    """Network receive/transmit rate snapshot."""

    receive_rate: float | None = None
    transmit_rate: float | None = None
    five_min_receive_rate: float | None = None
    five_min_transmit_rate: float | None = None
    receive_history: list[float] | None = None
    transmit_history: list[float] | None = None
    unit: str | None = None


@dataclass
class ResourceTelemetrySnapshot:
    """Focused host resource snapshot for the OTEL TUI."""

    summary: Dict[str, int]
    cpu: CpuUsage
    memory: UsagePair
    disk: UsagePair
    network: NetworkUsage
    latest_timestamp: datetime | None
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


def _attrs_key(attrs: Any, *, exclude: set[str] | None = None) -> str:
    if not isinstance(attrs, dict):
        return ""
    exclude = exclude or set()
    filtered = {key: value for key, value in attrs.items() if key not in exclude}
    return json.dumps(filtered, sort_keys=True, default=str)


def _state(attrs: Any) -> str:
    if not isinstance(attrs, dict):
        return ""
    return str(attrs.get("state") or attrs.get("direction") or "").lower()


def _attr_value(attrs: Any, key: str) -> str:
    if not isinstance(attrs, dict):
        return ""
    return str(attrs.get(key) or "")


def _rows_matching(numeric_df: pd.DataFrame, *needles: str) -> pd.DataFrame:
    if numeric_df.empty:
        return numeric_df
    lowered = numeric_df["name"].str.lower()
    mask = pd.Series([False] * len(numeric_df), index=numeric_df.index)
    for needle in needles:
        mask = mask | lowered.str.contains(needle, na=False)
    return numeric_df.loc[mask].dropna(subset=["timestamp", "value"]).copy()


def _latest_timestamp(numeric_df: pd.DataFrame) -> datetime | None:
    if numeric_df.empty:
        return None
    latest = numeric_df["timestamp"].dropna().max()
    if pd.isna(latest):
        return None
    return latest.to_pydatetime() if hasattr(latest, "to_pydatetime") else latest


def _latest_values_by_state(
    numeric_df: pd.DataFrame,
    *metric_needles: str,
    wanted_states: tuple[str, ...],
    units: tuple[str, ...] | None = None,
    exclude_name_needles: tuple[str, ...] = (),
    row_filter: Any | None = None,
    scope: str | None = None,
) -> UsagePair:
    rows = _rows_matching(numeric_df, *metric_needles)
    if rows.empty:
        return UsagePair()
    if units:
        rows = rows[rows["unit"].isin(units)]
    for needle in exclude_name_needles:
        rows = rows[~rows["name"].str.contains(needle, case=False, na=False)]
    if rows.empty:
        return UsagePair()
    if row_filter:
        rows = row_filter(rows)
    if rows.empty:
        return UsagePair()

    rows["_state"] = rows["attributes"].apply(_state)
    rows["_series"] = rows["attributes"].apply(
        lambda attrs: _attrs_key(attrs, exclude={"state"})
    )
    rows.sort_values("timestamp", inplace=True)
    latest_all = rows.groupby(["name", "_series", "_state"], as_index=False).tail(1)
    latest = latest_all[latest_all["_state"].isin(wanted_states)]
    if latest.empty:
        return UsagePair()
    unit_series = latest["unit"].dropna()
    unit = str(unit_series.iloc[0]) if not unit_series.empty else None
    state_values = latest.groupby("_state")["value"].sum().to_dict()
    total_value = float(latest_all["value"].sum())

    state_by_ts = (
        rows.groupby(["timestamp", "_series", "_state"], as_index=False)["value"]
        .mean()
        .groupby(["timestamp", "_state"])["value"]
        .sum()
        .unstack("_state")
        .sort_index()
    )
    history: list[float] = []
    for _, row in state_by_ts.iterrows():
        used = row.get("used")
        if pd.isna(used):
            continue
        total = float(row.dropna().sum())
        if total > 0:
            history.append(float(used) / total)

    return UsagePair(
        used=float(state_values["used"]) if "used" in state_values else None,
        free=float(state_values["free"]) if "free" in state_values else None,
        total_value=total_value,
        unit=unit,
        history=history[-MAX_POINTS_PER_SERIES:],
        scope=scope,
    )


def _memory_usage(numeric_df: pd.DataFrame) -> UsagePair:
    rows = _rows_matching(numeric_df, "memory.usage", "system.memory")
    if rows.empty:
        return UsagePair()
    rows = rows[rows["unit"].isin(("By", "bytes", "byte"))]
    rows = rows[
        ~rows["name"].str.contains("limit|usage_ratio|utilization", case=False, na=False)
    ]
    if rows.empty:
        return UsagePair()

    rows["_state"] = rows["attributes"].apply(_state)
    rows = rows[rows["_state"] != ""].copy()
    if rows.empty:
        return UsagePair()

    rows["_series"] = rows["attributes"].apply(
        lambda attrs: _attrs_key(attrs, exclude={"state"})
    )
    rows.sort_values("timestamp", inplace=True)
    latest = rows.groupby(["name", "_series", "_state"], as_index=False).tail(1)
    unit_series = latest["unit"].dropna()
    unit = str(unit_series.iloc[0]) if not unit_series.empty else None
    state_values = latest.groupby("_state")["value"].sum().to_dict()

    explicit_total = _latest_single_metric(
        numeric_df,
        "memory.limit",
        "memory.total",
        "system.memory.limit",
        "system.memory.total",
    )
    free = float(state_values["free"]) if "free" in state_values else None
    used = float(state_values["used"]) if "used" in state_values else None
    available = (
        float(state_values["available"]) if "available" in state_values else None
    )
    inactive = float(state_values["inactive"]) if "inactive" in state_values else 0.0
    cached = float(state_values["cached"]) if "cached" in state_values else 0.0
    buffered = float(state_values["buffered"]) if "buffered" in state_values else 0.0

    if free is None and available is not None:
        free = available
    total_value = explicit_total
    if total_value is None and used is not None:
        if available is not None:
            total_value = used + available
        elif free is not None:
            total_value = used + free + inactive + cached + buffered

    state_by_ts = (
        rows.groupby(["timestamp", "_series", "_state"], as_index=False)["value"]
        .mean()
        .groupby(["timestamp", "_state"])["value"]
        .sum()
        .unstack("_state")
        .sort_index()
    )
    history: list[float] = []
    for _, row in state_by_ts.iterrows():
        row_used = row.get("used")
        if pd.isna(row_used):
            continue
        row_available = row.get("available")
        row_free = row.get("free")
        if not pd.isna(row_available):
            row_total = float(row_used) + float(row_available)
        elif not pd.isna(row_free):
            extra = 0.0
            for state in ("inactive", "cached", "buffered"):
                state_value = row.get(state)
                if not pd.isna(state_value):
                    extra += float(state_value)
            row_total = float(row_used) + float(row_free) + extra
        else:
            continue
        if row_total > 0:
            history.append(float(row_used) / row_total)

    return UsagePair(
        used=used,
        free=free,
        total_value=total_value,
        unit=unit,
        history=history[-MAX_POINTS_PER_SERIES:],
    )


IGNORED_FILESYSTEM_TYPES = {
    "aufs",
    "autofs",
    "binfmt_misc",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devfs",
    "devpts",
    "devtmpfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "overlay",
    "proc",
    "pstore",
    "rpc_pipefs",
    "securityfs",
    "squashfs",
    "sysfs",
    "tmpfs",
    "tracefs",
}


def _filter_primary_filesystem_rows(rows: pd.DataFrame) -> pd.DataFrame:
    filtered = rows.copy()
    filtered["_mountpoint"] = filtered["attributes"].apply(
        lambda attrs: _attr_value(attrs, "mountpoint")
    )
    filtered["_fstype"] = filtered["attributes"].apply(
        lambda attrs: _attr_value(attrs, "type").lower()
    )
    filtered = filtered[~filtered["_fstype"].isin(IGNORED_FILESYSTEM_TYPES)]
    if filtered.empty:
        return filtered

    root_rows = filtered[filtered["_mountpoint"] == "/"]
    if not root_rows.empty:
        return root_rows

    latest_by_mount = filtered.groupby("_mountpoint")["value"].sum()
    if latest_by_mount.empty:
        return filtered
    preferred_mount = str(latest_by_mount.idxmax())
    return filtered[filtered["_mountpoint"] == preferred_mount]


def _five_min_average(
    points: list[tuple[Any, float]],
) -> float | None:
    if not points:
        return None
    latest_ts = points[-1][0]
    cutoff = latest_ts - timedelta(minutes=5)
    window_values = [value for ts, value in points if ts >= cutoff]
    if not window_values:
        return points[-1][1]
    return sum(window_values) / len(window_values)


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, value))


def _cpu_from_utilization(numeric_df: pd.DataFrame) -> CpuUsage:
    rows = _rows_matching(numeric_df, "cpu.utilization", "system.cpu.utilization")
    if rows.empty:
        return CpuUsage()

    rows["_state"] = rows["attributes"].apply(_state)
    state_by_ts = rows.pivot_table(
        index="timestamp", columns="_state", values="value", aggfunc="mean"
    ).sort_index()
    if state_by_ts.empty:
        return CpuUsage()

    points: list[tuple[Any, float]] = []
    for ts, row in state_by_ts.iterrows():
        state_values = {
            str(state): float(value)
            for state, value in row.dropna().items()
            if str(state)
        }
        if "idle" in state_values:
            total = sum(state_values.values())
            if total > 0 and total > state_values["idle"]:
                used = (total - state_values["idle"]) / total
            else:
                used = 1.0 - state_values["idle"]
        else:
            used = sum(state_values.values())
        points.append((ts, _clamp_ratio(used)))

    if not points:
        return CpuUsage()

    latest_used = points[-1][1]
    avg_used = _five_min_average(points)

    return CpuUsage(
        now_used_ratio=latest_used,
        now_free_ratio=1.0 - latest_used,
        five_min_used_ratio=avg_used,
        five_min_free_ratio=1.0 - avg_used if avg_used is not None else None,
        history=[value for _, value in points[-MAX_POINTS_PER_SERIES:]],
        source="utilization",
    )


def _cpu_from_time(numeric_df: pd.DataFrame) -> CpuUsage:
    rows = _rows_matching(numeric_df, "cpu.time", "system.cpu.time")
    if rows.empty:
        return CpuUsage()

    rows["_state"] = rows["attributes"].apply(_state)
    rows = rows[rows["_state"] != ""].copy()
    if rows.empty:
        return CpuUsage()

    rows["_series"] = rows["attributes"].apply(
        lambda attrs: _attrs_key(attrs, exclude={"state"})
    )
    rows.sort_values(["name", "_series", "_state", "timestamp"], inplace=True)
    rows["_prev_value"] = rows.groupby(["name", "_series", "_state"])["value"].shift(1)
    rows["_delta"] = rows["value"] - rows["_prev_value"]
    delta_rows = rows[rows["_delta"] >= 0].dropna(subset=["_delta"])
    if delta_rows.empty:
        return CpuUsage()

    state_deltas = (
        delta_rows.groupby(["timestamp", "_state"], as_index=False)["_delta"]
        .sum()
        .sort_values("timestamp")
    )
    points: list[tuple[Any, float]] = []
    for ts, group in state_deltas.groupby("timestamp"):
        by_state = group.set_index("_state")["_delta"].to_dict()
        total = sum(float(value) for value in by_state.values())
        if total <= 0:
            continue
        idle = float(by_state.get("idle", 0.0))
        used = _clamp_ratio((total - idle) / total)
        points.append((ts, used))

    if not points:
        return CpuUsage()

    latest_used = points[-1][1]
    avg_used = _five_min_average(points)
    return CpuUsage(
        now_used_ratio=latest_used,
        now_free_ratio=1.0 - latest_used,
        five_min_used_ratio=avg_used,
        five_min_free_ratio=1.0 - avg_used if avg_used is not None else None,
        history=[value for _, value in points[-MAX_POINTS_PER_SERIES:]],
        source="time",
    )


def _latest_single_metric(numeric_df: pd.DataFrame, *metric_needles: str) -> float | None:
    rows = _rows_matching(numeric_df, *metric_needles)
    if rows.empty:
        return None
    rows.sort_values("timestamp", inplace=True)
    return float(rows["value"].iloc[-1])


def _cpu_core_count(numeric_df: pd.DataFrame) -> int | None:
    rows = _rows_matching(
        numeric_df,
        "cpu.time",
        "system.cpu.time",
        "cpu.utilization",
        "system.cpu.utilization",
    )
    if rows.empty:
        return None
    cpu_ids = {
        _attr_value(attrs, "cpu")
        for attrs in rows["attributes"]
        if _attr_value(attrs, "cpu")
    }
    return len(cpu_ids) if cpu_ids else None


def _cpu_usage(numeric_df: pd.DataFrame) -> CpuUsage:
    usage = _cpu_from_utilization(numeric_df)
    if usage.now_used_ratio is None:
        usage = _cpu_from_time(numeric_df)

    usage.load_1m = _latest_single_metric(numeric_df, "load_average.1m", "load.1m")
    usage.load_5m = _latest_single_metric(numeric_df, "load_average.5m", "load.5m")
    usage.load_15m = _latest_single_metric(numeric_df, "load_average.15m", "load.15m")
    usage.logical_cpus = _cpu_core_count(numeric_df)
    return usage


def _network_usage(numeric_df: pd.DataFrame) -> NetworkUsage:
    rows = _rows_matching(numeric_df, "network.io", "network.packets")
    if rows.empty:
        return NetworkUsage()

    rows["_direction"] = rows["attributes"].apply(_state)
    rows = rows[rows["_direction"].isin({"receive", "transmit"})]
    if rows.empty:
        return NetworkUsage()

    rows["_series"] = rows["attributes"].apply(
        lambda attrs: _attrs_key(attrs, exclude={"direction"})
    )
    unit_series = rows["unit"].dropna()
    unit = str(unit_series.iloc[0]) if not unit_series.empty else None

    latest_rates = {"receive": 0.0, "transmit": 0.0}
    five_min_rates = {"receive": 0.0, "transmit": 0.0}
    rate_history: dict[str, dict[Any, float]] = {"receive": {}, "transmit": {}}
    has_latest = {"receive": False, "transmit": False}
    has_five_min = {"receive": False, "transmit": False}

    for (_metric_name, _series, direction), group in rows.groupby(
        ["name", "_series", "_direction"]
    ):
        ordered = group.sort_values("timestamp")
        previous = None
        for _, current in ordered.iterrows():
            if previous is None:
                previous = current
                continue
            seconds = (current["timestamp"] - previous["timestamp"]).total_seconds()
            delta = float(current["value"]) - float(previous["value"])
            if seconds > 0 and delta >= 0:
                ts = current["timestamp"]
                rate_history[direction][ts] = (
                    rate_history[direction].get(ts, 0.0) + delta / seconds
                )
            previous = current

        if len(ordered) >= 2:
            prev = ordered.iloc[-2]
            latest = ordered.iloc[-1]
            seconds = (latest["timestamp"] - prev["timestamp"]).total_seconds()
            delta = float(latest["value"]) - float(prev["value"])
            if seconds > 0 and delta >= 0:
                latest_rates[direction] += delta / seconds
                has_latest[direction] = True

        latest_ts = ordered["timestamp"].iloc[-1]
        window = ordered[ordered["timestamp"] >= latest_ts - timedelta(minutes=5)]
        if len(window) >= 2:
            first = window.iloc[0]
            latest = window.iloc[-1]
            seconds = (latest["timestamp"] - first["timestamp"]).total_seconds()
            delta = float(latest["value"]) - float(first["value"])
            if seconds > 0 and delta >= 0:
                five_min_rates[direction] += delta / seconds
                has_five_min[direction] = True

    return NetworkUsage(
        receive_rate=latest_rates["receive"] if has_latest["receive"] else None,
        transmit_rate=latest_rates["transmit"] if has_latest["transmit"] else None,
        five_min_receive_rate=(
            five_min_rates["receive"] if has_five_min["receive"] else None
        ),
        five_min_transmit_rate=(
            five_min_rates["transmit"] if has_five_min["transmit"] else None
        ),
        receive_history=[
            rate
            for _, rate in sorted(rate_history["receive"].items())[
                -MAX_POINTS_PER_SERIES:
            ]
        ],
        transmit_history=[
            rate
            for _, rate in sorted(rate_history["transmit"].items())[
                -MAX_POINTS_PER_SERIES:
            ]
        ],
        unit=unit,
    )


def _build_resource_snapshot(telemetry_raw: str | None) -> ResourceTelemetrySnapshot:
    telemetry_data, errors = _load_jsonl(telemetry_raw)
    summary = {"spans": 0, "logs": 0, "metric_points": 0}
    messages: list[str] = []

    if not telemetry_data:
        return ResourceTelemetrySnapshot(
            summary=summary,
            cpu=CpuUsage(),
            memory=UsagePair(),
            disk=UsagePair(),
            network=NetworkUsage(),
            latest_timestamp=None,
            messages=[
                "No telemetry data loaded yet. Host metrics will appear after the collector writes samples."
            ],
            errors=errors,
        )

    span_payloads, log_payloads, metric_payloads = _split_telemetry_payload(
        telemetry_data
    )
    _, numeric_df = _build_metric_frames(metric_payloads)
    summary = {
        "spans": len(_extract_span_records(span_payloads)),
        "logs": len(_extract_log_records(log_payloads)),
        "metric_points": len(numeric_df),
    }

    if errors:
        messages.append(f"Skipped {errors} malformed telemetry records during parsing.")
    if numeric_df.empty:
        messages.append("No numeric host metrics were found in the collector output.")

    snapshot = ResourceTelemetrySnapshot(
        summary=summary,
        cpu=_cpu_usage(numeric_df),
        memory=_memory_usage(numeric_df),
        disk=_latest_values_by_state(
            numeric_df,
            "filesystem.usage",
            "disk.usage",
            "system.filesystem",
            wanted_states=("used", "free"),
            units=("By", "bytes", "byte"),
            exclude_name_needles=("inode",),
            row_filter=_filter_primary_filesystem_rows,
            scope="root filesystem",
        ),
        network=_network_usage(numeric_df),
        latest_timestamp=_latest_timestamp(numeric_df),
        messages=messages,
        errors=errors,
    )
    return snapshot


def _format_percent(value: float | None) -> str:
    return f"{value * 100:,.1f}%" if value is not None else "N/A"


def _format_bytes(value: float | None) -> str:
    if value is None:
        return "N/A"
    units = ("B", "KB", "MB", "GB", "TB")
    scaled = float(value)
    unit = units[0]
    for unit in units:
        if abs(scaled) < 1024 or unit == units[-1]:
            break
        scaled /= 1024
    return f"{scaled:,.1f} {unit}"


def _format_value(value: float | None, unit: str | None) -> str:
    if value is None:
        return "N/A"
    if unit in {"By", "bytes", "byte"}:
        return _format_bytes(value)
    return f"{value:,.2f}{unit or ''}"


def _format_rate(value: float | None, unit: str | None) -> str:
    if value is None:
        return "N/A"
    if unit in {"By", "bytes", "byte"}:
        return f"{_format_bytes(value)}/s"
    return f"{value:,.2f}{unit or ''}/s"


def _format_load(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None else "N/A"


def _mini_sparkline(values: list[float] | None, *, ratio: bool = True) -> str:
    if not values:
        return "N/A"
    blocks = "▁▂▃▄▅▆▇█"
    raw_values = [float(value) for value in values if value is not None]
    if ratio:
        cleaned = [_clamp_ratio(value) for value in raw_values]
    else:
        max_value = max(raw_values) if raw_values else 0
        cleaned = [value / max_value if max_value > 0 else 0 for value in raw_values]
    if not cleaned:
        return "N/A"
    max_points = 32
    if len(cleaned) > max_points:
        cleaned = cleaned[-max_points:]
    return "".join(
        blocks[min(len(blocks) - 1, int(value * (len(blocks) - 1)))]
        for value in cleaned
    )


class OtelTelemetryPanel(VerticalScroll):
    """Non-blocking, focused OTEL host resource dashboard."""

    def __init__(
        self,
        infra: Infrastructure | None,
        bundle: Bundle | None,
        service: OtelDockerService | Any | None,
        refresh_seconds: int = 30,
    ) -> None:
        super().__init__()
        self.infra = infra
        self.bundle = bundle
        self.service = service
        self.refresh_seconds = refresh_seconds
        self.snapshot: ResourceTelemetrySnapshot | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="otel-telemetry-status")
        with Horizontal(id="otel-resource-row-1", classes="otel-resource-row"):
            yield Static("", id="otel-cpu-card", classes="otel-resource-card")
            yield Static("", id="otel-memory-card", classes="otel-resource-card")
        with Horizontal(id="otel-resource-row-2", classes="otel-resource-row"):
            yield Static("", id="otel-disk-card", classes="otel-resource-card")
            yield Static("", id="otel-network-card", classes="otel-resource-card")
        yield Static("", id="otel-telemetry-summary")

    @property
    def status(self) -> Static:
        return self.query_one("#otel-telemetry-status", Static)

    def on_mount(self) -> None:
        self.status.update("Loading OpenTelemetry host metrics...")
        self._render_placeholder()
        self.refresh_snapshot()
        self.set_interval(self.refresh_seconds, self.refresh_snapshot)

    def refresh_snapshot(self) -> None:
        app = self.app

        def fetch_snapshot() -> None:
            try:
                telemetry_raw = (
                    self.service.get_telemetry_data(self.bundle)
                    if self.service and self.bundle
                    else None
                )
                snapshot = _build_resource_snapshot(telemetry_raw)
            except Exception as exc:  # pragma: no cover - remote IO defensive path
                snapshot = ResourceTelemetrySnapshot(
                    summary={"spans": 0, "logs": 0, "metric_points": 0},
                    cpu=CpuUsage(),
                    memory=UsagePair(),
                    disk=UsagePair(),
                    network=NetworkUsage(),
                    latest_timestamp=None,
                    messages=[f"Failed to load OTEL telemetry: {exc}"],
                )
            app.call_from_thread(self._apply_snapshot, snapshot)

        app.run_worker(
            fetch_snapshot,
            thread=True,
            exclusive=True,
            group=f"otel-telemetry-{id(self)}",
        )

    def _apply_snapshot(self, snapshot: ResourceTelemetrySnapshot) -> None:
        self.snapshot = snapshot
        try:
            self._render_snapshot(snapshot)
        except NoMatches:
            return

    def _render_placeholder(self) -> None:
        pending = Panel(Text("Loading..."), title="OpenTelemetry", border_style="cyan")
        for selector in (
            "#otel-cpu-card",
            "#otel-memory-card",
            "#otel-disk-card",
            "#otel-network-card",
        ):
            self.query_one(selector, Static).update(pending)

    def _render_snapshot(self, snapshot: ResourceTelemetrySnapshot) -> None:
        timestamp = _ts_display(snapshot.latest_timestamp)
        messages = " ".join(snapshot.messages)
        self.status.update(
            f"Latest sample: {timestamp}"
            f" | Refreshes every {self.refresh_seconds}s"
            + (f" | {messages}" if messages else "")
        )
        self.query_one("#otel-cpu-card", Static).update(self._cpu_panel(snapshot.cpu))
        self.query_one("#otel-memory-card", Static).update(
            self._usage_panel("Memory", snapshot.memory)
        )
        self.query_one("#otel-disk-card", Static).update(
            self._usage_panel("Disk", snapshot.disk)
        )
        self.query_one("#otel-network-card", Static).update(
            self._network_panel(snapshot.network)
        )
        self.query_one("#otel-telemetry-summary", Static).update(
            self._summary_panel(snapshot)
        )

    def _cpu_panel(self, cpu: CpuUsage) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Used", justify="right")
        table.add_column("Free", justify="right")
        table.add_row(
            "Now (used/free)",
            _format_percent(cpu.now_used_ratio),
            _format_percent(cpu.now_free_ratio),
        )
        table.add_row(
            "5 min avg (used/free)",
            _format_percent(cpu.five_min_used_ratio),
            _format_percent(cpu.five_min_free_ratio),
        )
        table.add_row("Trend (used %)", _mini_sparkline(cpu.history), cpu.source or "-")
        table.add_row("Logical CPUs", str(cpu.logical_cpus) if cpu.logical_cpus else "N/A", "")
        table.add_row(
            "Load",
            f"1m {_format_load(cpu.load_1m)}",
            f"5m {_format_load(cpu.load_5m)} / 15m {_format_load(cpu.load_15m)}",
        )
        return Panel(table, title="CPU", border_style="green")

    def _usage_panel(self, title: str, usage: UsagePair) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Current used", _format_value(usage.used, usage.unit))
        table.add_row("Current free", _format_value(usage.free, usage.unit))
        table.add_row("Current total", _format_value(usage.total, usage.unit))
        table.add_row("Current used %", _format_percent(usage.used_ratio))
        table.add_row("Trend (used %)", _mini_sparkline(usage.history))
        if usage.scope:
            table.add_row("Scope", usage.scope)
        return Panel(table, title=title, border_style="green")

    def _network_panel(self, network: NetworkUsage) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Receive", justify="right")
        table.add_column("Transmit", justify="right")
        table.add_row(
            "Now rate",
            _format_rate(network.receive_rate, network.unit),
            _format_rate(network.transmit_rate, network.unit),
        )
        table.add_row(
            "5 min avg rate",
            _format_rate(network.five_min_receive_rate, network.unit),
            _format_rate(network.five_min_transmit_rate, network.unit),
        )
        table.add_row(
            "Trend",
            _mini_sparkline(network.receive_history, ratio=False),
            _mini_sparkline(network.transmit_history, ratio=False),
        )
        return Panel(table, title="Network", border_style="green")

    def _summary_panel(self, snapshot: ResourceTelemetrySnapshot) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        for key, value in snapshot.summary.items():
            table.add_row(key.replace("_", " ").title(), str(value))
        return Panel(table, title="Collector Output", border_style="blue")


def settings(
    infra: Infrastructure,
    bundle: Bundle,
    service: OtelDockerService,
) -> OtelTelemetryPanel:
    """Return a Textual container visualising OTEL telemetry."""

    return OtelTelemetryPanel(infra, bundle, service)
