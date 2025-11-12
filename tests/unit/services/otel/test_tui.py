from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from mlox.services.otel.tui import MetricGroup, OtelTelemetryPanel, _build_snapshot, tui_settings


@dataclass
class DummyBundle:
    name: str = "bundle"


@dataclass
class DummyService:
    telemetry: str

    def get_telemetry_data(self, bundle):  # pragma: no cover - simple passthrough
        return self.telemetry


def _jsonl(*records: dict) -> str:
    return "\n".join(json.dumps(record) for record in records)


def test_build_snapshot_groups_metrics() -> None:
    telemetry = _jsonl(
        {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "name": "op",
                                    "startTimeUnixNano": "1000",
                                    "endTimeUnixNano": "2000",
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "resourceLogs": [
                {
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {"timeUnixNano": "1000", "body": {"stringValue": "message"}}
                            ]
                        }
                    ]
                }
            ]
        },
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "cpu.load.1m",
                                    "unit": "1",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "1000",
                                                "asDouble": 0.5,
                                                "attributes": [
                                                    {"key": "host", "value": {"stringValue": "srv"}}
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "2000",
                                                "asDouble": 0.75,
                                            },
                                        ]
                                    },
                                },
                                {
                                    "name": "memory.usage",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {"timeUnixNano": "1000", "asInt": 100},
                                            {"timeUnixNano": "2000", "asInt": 200},
                                        ]
                                    },
                                },
                                {
                                    "name": "network.packets.sent",
                                    "unit": "1",
                                    "sum": {
                                        "dataPoints": [
                                            {"timeUnixNano": "1000", "value": 10},
                                            {"timeUnixNano": "2000", "value": 20},
                                        ]
                                    },
                                },
                            ]
                        }
                    ]
                }
            ]
        },
    )

    snapshot = _build_snapshot(telemetry)

    assert snapshot.summary["spans"] == 1
    assert snapshot.summary["logs"] == 1
    assert snapshot.summary["metric_points"] == 6
    assert "cpu_utilization" in snapshot.groups
    assert "memory_usage" in snapshot.groups
    assert "network_throughput" in snapshot.groups
    cpu_group = snapshot.groups["cpu_utilization"]
    assert isinstance(cpu_group, MetricGroup)
    assert cpu_group.values[-1] == pytest.approx(0.75)
    assert cpu_group.unit == "1"


def test_tui_settings_returns_panel() -> None:
    telemetry = _jsonl({"resourceMetrics": []})
    panel = tui_settings(
        infra=None,  # type: ignore[arg-type]
        bundle=DummyBundle(),
        service=DummyService(telemetry=telemetry),
    )

    assert isinstance(panel, OtelTelemetryPanel)


def test_build_snapshot_handles_empty_payload() -> None:
    snapshot = _build_snapshot("")

    assert snapshot.summary["metric_points"] == 0
    assert not snapshot.groups
    assert any("No telemetry data" in msg for msg in snapshot.messages)
