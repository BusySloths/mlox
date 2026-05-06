from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from mlox.tui.services.otel import (
    MetricGroup,
    OtelTelemetryPanel,
    _build_resource_snapshot,
    _build_snapshot,
    settings,
)


@dataclass
class DummyBundle:
    name: str = "bundle"


@dataclass
class DummyService:
    telemetry: str
    calls: int = 0

    def get_telemetry_data(self, bundle):  # pragma: no cover - simple passthrough
        self.calls += 1
        return self.telemetry


def _jsonl(*records: dict) -> str:
    return "\n".join(json.dumps(record) for record in records)


def _attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"stringValue": value}}


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
    assert cpu_group.series
    first_series = cpu_group.series[0]
    assert first_series.values[-1] == pytest.approx(0.75)
    assert first_series.unit == "1"


def test_tui_settings_returns_panel() -> None:
    telemetry = _jsonl({"resourceMetrics": []})
    service = DummyService(telemetry=telemetry)
    panel = settings(
        infra=None,  # type: ignore[arg-type]
        bundle=DummyBundle(),
        service=service,
    )

    assert isinstance(panel, OtelTelemetryPanel)
    assert service.calls == 0


def test_build_snapshot_handles_empty_payload() -> None:
    snapshot = _build_snapshot("")

    assert snapshot.summary["metric_points"] == 0
    assert not snapshot.groups
    assert any("No telemetry data" in msg for msg in snapshot.messages)


def test_resource_snapshot_extracts_host_resource_view() -> None:
    telemetry = _jsonl(
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "system.cpu.utilization",
                                    "unit": "1",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "1000000000",
                                                "asDouble": 0.80,
                                                "attributes": [_attr("state", "idle")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asDouble": 0.70,
                                                "attributes": [_attr("state", "idle")],
                                            },
                                        ]
                                    },
                                },
                                {
                                    "name": "system.memory.usage",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 300,
                                                "attributes": [_attr("state", "used")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 700,
                                                "attributes": [_attr("state", "free")],
                                            },
                                        ]
                                    },
                                },
                                {
                                    "name": "system.filesystem.usage",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 400,
                                                "attributes": [
                                                    _attr("mountpoint", "/"),
                                                    _attr("state", "used"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 600,
                                                "attributes": [
                                                    _attr("mountpoint", "/"),
                                                    _attr("state", "free"),
                                                ],
                                            },
                                        ]
                                    },
                                },
                                {
                                    "name": "system.network.io",
                                    "unit": "By",
                                    "sum": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "1000000000",
                                                "asInt": 1000,
                                                "attributes": [
                                                    _attr("device", "eth0"),
                                                    _attr("direction", "receive"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 2200,
                                                "attributes": [
                                                    _attr("device", "eth0"),
                                                    _attr("direction", "receive"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "1000000000",
                                                "asInt": 500,
                                                "attributes": [
                                                    _attr("device", "eth0"),
                                                    _attr("direction", "transmit"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 1100,
                                                "attributes": [
                                                    _attr("device", "eth0"),
                                                    _attr("direction", "transmit"),
                                                ],
                                            },
                                        ]
                                    },
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    )

    snapshot = _build_resource_snapshot(telemetry)

    assert snapshot.cpu.now_used_ratio == pytest.approx(0.30)
    assert snapshot.cpu.five_min_used_ratio == pytest.approx(0.25)
    assert snapshot.memory.used == pytest.approx(300)
    assert snapshot.memory.free == pytest.approx(700)
    assert snapshot.memory.used_ratio == pytest.approx(0.3)
    assert snapshot.memory.history == pytest.approx([0.3])
    assert snapshot.disk.used == pytest.approx(400)
    assert snapshot.disk.free == pytest.approx(600)
    assert snapshot.disk.history == pytest.approx([0.4])
    assert snapshot.network.receive_rate == pytest.approx(20)
    assert snapshot.network.transmit_rate == pytest.approx(10)
    assert snapshot.network.receive_history == pytest.approx([20])
    assert snapshot.network.transmit_history == pytest.approx([10])


def test_resource_snapshot_derives_cpu_from_cumulative_cpu_time() -> None:
    telemetry = _jsonl(
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "system.cpu.time",
                                    "unit": "s",
                                    "sum": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "1000000000",
                                                "asDouble": 10,
                                                "attributes": [
                                                    _attr("cpu", "0"),
                                                    _attr("state", "idle"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "1000000000",
                                                "asDouble": 5,
                                                "attributes": [
                                                    _attr("cpu", "0"),
                                                    _attr("state", "user"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asDouble": 16,
                                                "attributes": [
                                                    _attr("cpu", "0"),
                                                    _attr("state", "idle"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asDouble": 9,
                                                "attributes": [
                                                    _attr("cpu", "0"),
                                                    _attr("state", "user"),
                                                ],
                                            },
                                        ]
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )

    snapshot = _build_resource_snapshot(telemetry)

    assert snapshot.cpu.source == "time"
    assert snapshot.cpu.now_used_ratio == pytest.approx(0.4)
    assert snapshot.cpu.now_free_ratio == pytest.approx(0.6)
    assert snapshot.cpu.history == pytest.approx([0.4])


def test_resource_snapshot_uses_byte_disk_metrics_not_inodes() -> None:
    telemetry = _jsonl(
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "system.filesystem.inodes.usage",
                                    "unit": "{inodes}",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 1,
                                                "attributes": [_attr("state", "used")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 99,
                                                "attributes": [_attr("state", "free")],
                                            },
                                        ]
                                    },
                                },
                                {
                                    "name": "system.filesystem.usage",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 1024,
                                                "attributes": [_attr("state", "used")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 3072,
                                                "attributes": [_attr("state", "free")],
                                            },
                                        ]
                                    },
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    )

    snapshot = _build_resource_snapshot(telemetry)

    assert snapshot.disk.unit == "By"
    assert snapshot.disk.used == pytest.approx(1024)
    assert snapshot.disk.free == pytest.approx(3072)
