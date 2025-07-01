import json  # For parsing JSON
import pandas as pd  # Optional: for displaying as a table
import streamlit as st

from datetime import datetime
from streamlit_timeline import st_timeline  # type: ignore


from typing import List, Dict


from mlox.services.otel.docker import OtelDockerService
from mlox.infra import Infrastructure, Bundle


def load_jsonl(raw):
    """Loads data from a JSON Lines file."""
    data = []
    try:
        for line in raw.splitlines():
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                st.error(f"Error decoding JSON from line: {line.strip()} - {e}")
    except Exception as e:
        st.error(f"An error occurred while reading the file: {e}")
    return data


def setup(infra: Infrastructure, bundle: Bundle) -> Dict:
    params = dict()
    c1, c2 = st.columns(2)
    params["${MLOX_RELIC_KEY}"] = c1.text_input("New Relic OTLP Key", key="relic_key")
    params["${MLOX_RELIC_ENDPOINT}"] = c2.text_input(
        "New Relic OTLP Endpoint",
        value="https://otlp.eu01.nr-data.net:4317",
        key="relic_endpoint",
    )
    return params


def settings(infra: Infrastructure, bundle: Bundle, service: OtelDockerService):
    # st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    # Get the path to the (copied) telemetry data file
    telemetry_raw_data = service.get_telemetry_data(bundle)
    telemetry_data = load_jsonl(telemetry_raw_data)

    if not telemetry_data:
        st.info("No telemetry data loaded or file was empty/corrupt.")
        return

    # st.subheader("Raw Telemetry Data (JSONL)")
    # Display each JSON object

    spans = list()
    logs = list()
    metrics = list()
    for item in telemetry_data:
        if "resourceSpans" in item:
            spans.append(item)
        elif "resourceLogs" in item:
            logs.append(item)
        elif "resourceMetrics" in item:
            metrics.append(item)

    tab_table, tab_timeline = st.tabs(["Table", "Timeline"])

    with tab_table:
        st.write(f"Spans: {len(spans)}")
        st.write(f"Logs: {len(logs)}")
        st.write(f"Metrics: {len(metrics)}")
        # st.write(logs[0])
        # # Optional: Display as a Pandas DataFrame if the structure is somewhat consistent
        # try:
        #     df = pd.DataFrame(telemetry_data)
        #     st.subheader("Telemetry Data (Table View)")
        #     st.dataframe(df)
        # except Exception as e:
        #     st.warning(f"Could not display data as a table: {e}")
        plot_logs(logs)

    with tab_timeline:
        plot_timeline(spans, logs, metrics)


def plot_logs(logs: List):
    for log in logs:
        st.write(
            log["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["body"][
                "stringValue"
            ]
        )


def plot_timeline(spans, logs, metrics, st_key: str | None = None):
    items: List = list()

    id: int = 0
    for span in spans:
        s = span["resourceSpans"][0]["scopeSpans"][0]["spans"]
        # st.write(s)
        for i in range(len(s)):
            start = s[i]["startTimeUnixNano"]
            start = datetime.fromtimestamp(float(start) / 1e9).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            end = s[i]["endTimeUnixNano"]
            end = datetime.fromtimestamp(float(end) / 1e9 + 100).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            items.append(
                {
                    "start": start,
                    "end": end,
                    "id": id,
                    "content": s[i]["name"],
                    "group": 2,
                }
            )
            id += 1

    # st.write(logs[0]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0])
    for log in logs:
        l = log["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
        # st.write(l)
        start = l["observedTimeUnixNano"]
        start = datetime.fromtimestamp(float(start) / 1e9).strftime("%Y-%m-%d %H:%M:%S")
        items.append(
            {
                "start": start,
                "id": id,
                "content": l["severityText"],
                # "content": {
                #     "severity": l["severityText"],
                #     "message": l["body"]["stringValue"],
                # },
                "group": 1,
            }
        )
        id += 1

    groups = [
        # {"id": 0, "content": "Project", "nestedGroups": [1, 2, 3]},
        {"id": 1, "content": "Logs"},
        # {"id": 2, "content": "WBS ", "nestedGroups": [3]},
        # {"id": 2, "content": "Traces", "height": "200px"},
        {"id": 2, "content": "Traces"},
        # {"id": 2, "content": "WP"},
        # {"id": 3, "content": "Metrics", "height": "200px"},
        {"id": 3, "content": "Metrics"},
    ]
    selection = st_timeline(
        items,
        groups=groups,
        options={"editable": False, "selectable": True, "stack": True},
        height="500px",
        key=f"{st_key}_timeline",
    )
    if selection:
        st.write(selection.get("content", "select something"))
