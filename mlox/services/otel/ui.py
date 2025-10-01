import json
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st
from streamlit_timeline import st_timeline  # type: ignore

from mlox.infra import Bundle, Infrastructure
from mlox.services.otel.docker import OtelDockerService

STANDARD_METRIC_GROUPS: dict[str, tuple[str, ...]] = {
    "CPU Utilization": ("cpu.load",),
    "Memory Usage": ("memory", "mem"),
    "Network Throughput": ("network.packets", "net.packets"),
}
MAX_LOGS_DISPLAYED = 20


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
    return ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "Unknown time"


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


def _render_summary(
    spans: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    metric_count: int,
) -> None:
    col_traces, col_logs, col_metrics = st.columns(3)
    col_traces.metric("Traces", len(spans))
    col_logs.metric("Logs", len(logs))
    col_metrics.metric("Metric Points", metric_count)
    st.caption("Insight generated from OpenTelemetry data pulled via the collector.")


def _render_logs(log_records: list[dict[str, Any]]) -> None:
    st.markdown("#### Recent Logs")
    if not log_records:
        st.caption("No logs captured yet.")
        return

    sorted_logs = sorted(
        log_records,
        key=lambda record: record.get("timeUnixNano")
        or record.get("observedTimeUnixNano")
        or 0,
    )
    recent_logs = sorted_logs[-MAX_LOGS_DISPLAYED:]

    for log_entry in recent_logs:
        timestamp = _timestamp_from_nanos(
            log_entry.get("timeUnixNano") or log_entry.get("observedTimeUnixNano")
        )
        severity = log_entry.get("severityText", "INFO")
        body = log_entry.get("body", {})
        message = body.get("stringValue") if isinstance(body, dict) else str(body)
        attributes = _attributes_list_to_dict(log_entry.get("attributes"))

        st.markdown(f"**{severity}** · `{_format_timestamp(timestamp)}`")
        if attributes:
            st.caption(_format_attributes(attributes))
        st.write(message or "No log payload provided.")
        st.divider()


def _render_metric_charts(
    numeric_df: pd.DataFrame,
    selected_names: list[str],
) -> None:
    if numeric_df.empty:
        st.caption("Numeric metrics will appear here once available.")
        return

    filtered = numeric_df
    if selected_names:
        filtered = numeric_df[numeric_df["name"].isin(selected_names)]

    if not filtered.empty:
        chart_df = (
            filtered.sort_values("timestamp")
            .pivot_table(
                index="timestamp", columns="series", values="value", aggfunc="mean"
            )
            .sort_index()
        )
        st.line_chart(chart_df, use_container_width=True, height=280)
    else:
        st.caption("Selected metrics do not contain numeric datapoints.")

    with st.expander("Standard Metric Views", expanded=False):
        found_standard = False
        for label, keywords in STANDARD_METRIC_GROUPS.items():
            mask = numeric_df["name"].str.contains(
                "|".join(keywords), case=False, na=False
            )
            group_df = numeric_df[mask].sort_values("timestamp")
            if group_df.empty:
                continue
            found_standard = True
            st.markdown(f"**{label}**")
            chart_df = group_df.pivot_table(
                index="timestamp", columns="series", values="value", aggfunc="mean"
            ).sort_index()
            st.line_chart(chart_df, use_container_width=True, height=220)
        if not found_standard:
            st.caption("Standard CPU, memory, or network metrics were not detected.")


def _render_metrics_section(display_df: pd.DataFrame, numeric_df: pd.DataFrame) -> None:
    st.markdown("#### Metrics")
    if display_df.empty:
        st.caption("No metrics captured yet.")
        return

    all_names = sorted(display_df["name"].unique())
    default_selection = all_names[: min(3, len(all_names))]
    selected_names = st.multiselect(
        "Select metrics to inspect",
        all_names,
        default=default_selection,
    )

    table_df = display_df
    if selected_names:
        table_df = display_df[display_df["name"].isin(selected_names)]

    st.dataframe(
        table_df[
            ["timestamp", "name", "type", "value", "unit", "attributes", "description"]
        ],
        use_container_width=True,
    )
    _render_metric_charts(numeric_df, selected_names)


def _plot_timeline(
    span_records: list[dict[str, Any]],
    log_records: list[dict[str, Any]],
    key: str,
) -> None:
    items: list[dict[str, Any]] = []
    item_id = 0

    for log_entry in log_records:
        timestamp = _timestamp_from_nanos(
            log_entry.get("timeUnixNano") or log_entry.get("observedTimeUnixNano")
        )
        if not timestamp:
            continue
        body = log_entry.get("body", {})
        message = body.get("stringValue") if isinstance(body, dict) else str(body)
        items.append(
            {
                "id": item_id,
                "start": _format_timestamp(timestamp),
                "content": log_entry.get("severityText", "LOG"),
                "title": message,
                "group": 1,
            }
        )
        item_id += 1

    for span in span_records:
        start = _timestamp_from_nanos(span.get("startTimeUnixNano"))
        end = _timestamp_from_nanos(span.get("endTimeUnixNano")) or start
        if not start:
            continue
        items.append(
            {
                "id": item_id,
                "start": _format_timestamp(start),
                "end": _format_timestamp(end),
                "content": span.get("name", "span"),
                "group": 2,
            }
        )
        item_id += 1

    if not items:
        st.caption("Timeline data appears once traces or logs are collected.")
        return

    groups = [
        {"id": 1, "content": "Logs"},
        {"id": 2, "content": "Traces"},
    ]

    selection = st_timeline(
        items,
        groups=groups,
        options={"editable": False, "selectable": True, "stack": True},
        height="320px",
        key=f"{key}-timeline",
    )
    if selection:
        selection_content = selection.get("title") or selection.get("content")
        if selection_content:
            st.caption(f"Selected: {selection_content}")


def setup(infra: Infrastructure, bundle: Bundle) -> dict[str, str]:
    params: dict[str, str] = {}
    col_key, col_endpoint = st.columns(2)
    params["${MLOX_RELIC_KEY}"] = col_key.text_input(
        "New Relic OTLP Key", key="relic_key"
    )
    params["${MLOX_RELIC_ENDPOINT}"] = col_endpoint.text_input(
        "New Relic OTLP Endpoint",
        value="https://otlp.eu01.nr-data.net:4317",
        key="relic_endpoint",
    )
    return params


def settings(infra: Infrastructure, bundle: Bundle, service: OtelDockerService) -> None:
    telemetry_raw_data = service.get_telemetry_data(bundle)
    telemetry_data, errors = _load_jsonl(telemetry_raw_data)
    if errors:
        st.warning(f"Skipped {errors} malformed telemetry records during parsing.")

    if not telemetry_data:
        st.info(
            "No telemetry data loaded yet. Trigger traffic to populate the collector."
        )
        return

    span_payloads, log_payloads, metric_payloads = _split_telemetry_payload(
        telemetry_data
    )
    span_records = _extract_span_records(span_payloads)
    log_records = _extract_log_records(log_payloads)
    display_df, numeric_df = _build_metric_frames(metric_payloads)

    overview_tab, timeline_tab = st.tabs(["Overview", "Timeline"])

    with overview_tab:
        _render_summary(span_records, log_records, len(display_df))
        st.divider()
        _render_logs(log_records)
        st.divider()
        _render_metrics_section(display_df, numeric_df)

    with timeline_tab:
        _plot_timeline(span_records, log_records, service.uuid)
