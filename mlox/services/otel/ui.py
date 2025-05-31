import json  # For parsing JSON
import pandas as pd  # Optional: for displaying as a table
import streamlit as st

from typing import List


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


def settings(infra: Infrastructure, bundle: Bundle, service: OtelDockerService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")

    # Get the path to the (copied) telemetry data file
    telemetry_raw_data = service.get_telemetry_data(bundle)
    telemetry_data = load_jsonl(telemetry_raw_data)

    if not telemetry_data:
        st.info("No telemetry data loaded or file was empty/corrupt.")
        st.stop()

    st.subheader("Raw Telemetry Data (JSONL)")
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

    st.write(f"Spans: {len(spans)}")
    st.write(f"Logs: {len(logs)}")
    st.write(f"Metrics: {len(metrics)}")
    st.write(logs[0])

    # # Optional: Display as a Pandas DataFrame if the structure is somewhat consistent
    # try:
    #     df = pd.DataFrame(telemetry_data)
    #     st.subheader("Telemetry Data (Table View)")
    #     st.dataframe(df)
    # except Exception as e:
    #     st.warning(f"Could not display data as a table: {e}")
    plot_logs(logs)


def plot_logs(logs: List):
    for log in logs:
        st.write(
            log["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["body"][
                "stringValue"
            ]
        )
