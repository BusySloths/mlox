"""Parse OpenTelemetry collector JSONL exports into spans, logs and metric frames.

Shared by the TUI telemetry view; independent of any UI framework.
"""

import json
from datetime import datetime
from typing import Any

import pandas as pd

STANDARD_METRIC_GROUPS: dict[str, tuple[str, ...]] = {
    "CPU Utilization": ("cpu.load",),
    "Memory Usage": ("memory", "mem"),
    "Network Throughput": ("network.packets", "net.packets"),
}


def _load_jsonl(raw: str | None) -> tuple[list[dict[str, Any]], int]:
    if not raw:
        return [], 0

    data: list[dict[str, Any]] = []
    errors = 0
    for line in raw.splitlines():
        snippet = line.strip()
        if not snippet:
            continue
        try:
            data.append(json.loads(snippet))
        except json.JSONDecodeError:
            errors += 1
    return data, errors


def _split_telemetry_payload(
    payload: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    spans: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []

    for entry in payload:
        if "resourceSpans" in entry:
            spans.append(entry)
        elif "resourceLogs" in entry:
            logs.append(entry)
        elif "resourceMetrics" in entry:
            metrics.append(entry)
    return spans, logs, metrics


def _attributes_list_to_dict(attributes: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not attributes:
        return result
    for attr in attributes:
        key = attr.get("key")
        value_dict = attr.get("value", {}) if isinstance(attr, dict) else {}
        value = next(iter(value_dict.values()), None)
        if key:
            result[key] = value
    return result


def _timestamp_from_nanos(raw_ts: Any) -> datetime | None:
    if raw_ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(raw_ts) / 1e9)
    except (TypeError, ValueError):
        return None


def _format_timestamp(ts: datetime | None) -> str:
    return ts.isoformat(timespec="milliseconds") if ts else "Unknown time"


def _format_attributes(attributes: dict[str, Any] | None) -> str:
    if not attributes:
        return ""
    return ", ".join(f"{key}={value}" for key, value in attributes.items())


def _format_value_display(value: Any) -> Any:
    if isinstance(value, dict):
        return ", ".join(f"{key}={val}" for key, val in value.items())
    return value


def _format_series_label(name: str, attributes: dict[str, Any] | None) -> str:
    if not attributes:
        return name
    preferred_keys = ("host", "instance", "pod", "container", "service")
    highlights = [
        f"{key}={attributes[key]}" for key in preferred_keys if key in attributes
    ]
    if not highlights:
        highlights = [f"{key}={value}" for key, value in attributes.items()]
    highlight = ", ".join(highlights)
    return f"{name} ({highlight})" if highlight else name


def _extract_span_records(span_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in span_payloads:
        for resource in payload.get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                records.extend(scope.get("spans", []))
    return records


def _extract_log_records(log_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in log_payloads:
        for resource in payload.get("resourceLogs", []):
            for scope in resource.get("scopeLogs", []):
                records.extend(scope.get("logRecords", []))
    return records


def _build_metric_frames(
    metric_payloads: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    records: list[dict[str, Any]] = []
    for metric_blob in metric_payloads:
        for resource_metric in metric_blob.get("resourceMetrics", []):
            for scope_metric in resource_metric.get("scopeMetrics", []):
                for metric in scope_metric.get("metrics", []):
                    metric_name = metric.get("name", "unknown")
                    metric_desc = metric.get("description", "")
                    metric_unit = metric.get("unit", "")
                    metric_type = "unknown"
                    data_points: list[dict[str, Any]] = []

                    if "sum" in metric:
                        metric_type = "sum"
                        data_points = metric["sum"].get("dataPoints", [])
                    elif "gauge" in metric:
                        metric_type = "gauge"
                        data_points = metric["gauge"].get("dataPoints", [])
                    elif "histogram" in metric:
                        metric_type = "histogram"
                        data_points = metric["histogram"].get("dataPoints", [])

                    for data_point in data_points:
                        timestamp = _timestamp_from_nanos(
                            data_point.get("timeUnixNano")
                        )
                        attributes = _attributes_list_to_dict(
                            data_point.get("attributes")
                        )

                        numeric_value: float | None = None
                        value_display: Any
                        if metric_type == "histogram":
                            count = data_point.get("count")
                            total = data_point.get("sum")
                            value_display = {"count": count, "sum": total}
                        else:
                            raw_value = data_point.get("asDouble")
                            if raw_value is None:
                                raw_value = data_point.get("asInt")
                            if raw_value is None:
                                raw_value = data_point.get("value")
                            try:
                                numeric_value = float(raw_value)
                                value_display = numeric_value
                            except (TypeError, ValueError):
                                value_display = raw_value

                        records.append(
                            {
                                "timestamp": timestamp,
                                "name": metric_name,
                                "type": metric_type,
                                "unit": metric_unit,
                                "description": metric_desc,
                                "attributes": attributes,
                                "value_display": value_display,
                                "numeric_value": numeric_value,
                            }
                        )

    if not records:
        base_columns = [
            "timestamp",
            "name",
            "type",
            "value",
            "unit",
            "attributes",
            "description",
        ]
        numeric_columns = base_columns + ["series"]
        return pd.DataFrame(columns=base_columns), pd.DataFrame(columns=numeric_columns)

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    numeric_df = df.dropna(subset=["numeric_value"]).copy()
    if not numeric_df.empty:
        numeric_df["timestamp"] = pd.to_datetime(numeric_df["timestamp"])
        numeric_df["value"] = numeric_df["numeric_value"].astype(float)
        numeric_df["series"] = numeric_df.apply(
            lambda row: _format_series_label(row["name"], row["attributes"]),
            axis=1,
        )

    display_df = df.copy()
    display_df["value"] = display_df["value_display"].apply(_format_value_display)
    display_df["attributes"] = display_df["attributes"].apply(_format_attributes)

    display_df = display_df.drop(
        columns=["value_display", "numeric_value"], errors="ignore"
    )
    numeric_df = numeric_df.drop(
        columns=["value_display", "numeric_value"], errors="ignore"
    )

    return display_df, numeric_df
