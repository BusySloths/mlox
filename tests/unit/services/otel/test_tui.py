from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static

from mlox.tui.services.otel import (
    MetricGroup,
    OtelServicePanel,
    OtelTelemetryPanel,
    _destination_validation_error,
    _influx_service_options,
    _destination_update_values,
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
    file_destination: bool = True
    influx_service_uuid: str | None = None
    grafana_cloud_destination: bool = False
    grafana_cloud_endpoint: str = ""
    grafana_cloud_key: str = ""
    new_relic_destination: bool = False
    relic_endpoint: str = ""
    relic_key: str = ""
    diagnostic_exporter: bool = False

    def get_telemetry_data(self, bundle):  # pragma: no cover - simple passthrough
        self.calls += 1
        return self.telemetry


class OtelPanelTestApp(App):
    def __init__(self, panel: OtelTelemetryPanel) -> None:
        super().__init__()
        self.panel = panel

    def compose(self) -> ComposeResult:
        yield self.panel


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

    assert isinstance(panel, OtelServicePanel)
    assert service.calls == 0


def test_destination_update_stores_only_the_selected_influx_service_uuid() -> None:
    service = SimpleNamespace(
        grafana_cloud_key="stored-grafana-key", relic_key="stored-relic-key"
    )

    values = _destination_update_values(
        service,
        file_destination=True,
        influx_service_uuid="influx-service-uuid",
        grafana_cloud_destination=True,
        grafana_cloud_endpoint=" https://grafana ",
        grafana_cloud_key="",
        new_relic_destination=False,
        relic_endpoint=" https://newrelic ",
        relic_key="",
        diagnostic_exporter=False,
    )

    assert values["influx_service_uuid"] == "influx-service-uuid"
    assert values["grafana_cloud_key"] == "stored-grafana-key"
    assert values["relic_key"] == "stored-relic-key"
    assert not {"influx_token", "influx_endpoint", "influx_bucket"} & set(values)


def test_influx_service_options_only_list_binding_capable_databases() -> None:
    influx = SimpleNamespace(
        name="Telemetry Influx",
        uuid="influx-uuid",
        capabilities={"database"},
        get_influx_env_binding=lambda: {},
    )
    unrelated = SimpleNamespace(
        name="PostgreSQL", uuid="postgres-uuid", capabilities={"database"}
    )
    infra = SimpleNamespace(bundles=[SimpleNamespace(services=[influx, unrelated])])

    assert _influx_service_options(infra, None) == [
        ("Telemetry Influx (influx-u)", "influx-uuid")
    ]


def test_destination_validation_requires_hosted_destination_api_keys() -> None:
    assert _destination_validation_error(
        {
            "grafana_cloud_destination": True,
            "grafana_cloud_endpoint": "https://grafana.example/otlp",
            "grafana_cloud_key": "",
            "new_relic_destination": False,
        }
    ) == "Grafana Cloud needs both an OTLP endpoint and an API key."


async def _mounted_otel_service_panel_has_destination_button() -> str:
    panel = settings(
        infra=None,  # type: ignore[arg-type]
        bundle=DummyBundle(),  # type: ignore[arg-type]
        service=DummyService(telemetry=_jsonl({"resourceMetrics": []})),
    )
    app = OtelPanelTestApp(panel)  # type: ignore[arg-type]
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        label = str(app.query_one("#otel-open-destinations", Button).label)
    return label


def test_otel_service_panel_mounts_destination_button() -> None:
    label = asyncio.run(_mounted_otel_service_panel_has_destination_button())

    assert label == "Configure Collector Destinations"


async def _opened_destination_dialog_has_api_key_controls() -> tuple[str, str]:
    panel = settings(
        infra=None,  # type: ignore[arg-type]
        bundle=DummyBundle(),  # type: ignore[arg-type]
        service=DummyService(telemetry=_jsonl({"resourceMetrics": []})),
    )
    app = OtelPanelTestApp(panel)  # type: ignore[arg-type]
    async with app.run_test() as pilot:
        await pilot.click("#otel-open-destinations")
        await pilot.pause(0.1)
        title = app.screen.query_one("#otel-destinations-title", Static).render()
        grafana_key = app.screen.query_one("#otel-grafana-key", Input).placeholder
        relic_key = app.screen.query_one("#otel-relic-key", Input).placeholder
    return str(title), f"{grafana_key}|{relic_key}"


def test_otel_destination_dialog_exposes_hosted_destination_api_keys() -> None:
    title, key_placeholders = asyncio.run(_opened_destination_dialog_has_api_key_controls())

    assert title == "COLLECTOR DESTINATIONS"
    assert "Required when enabled" in key_placeholders


async def _mounted_otel_panel_snapshot() -> tuple[int, int | None]:
    telemetry = _jsonl({"resourceMetrics": []})
    service = DummyService(telemetry=telemetry)
    panel = OtelTelemetryPanel(
        infra=None,  # type: ignore[arg-type]
        bundle=DummyBundle(),  # type: ignore[arg-type]
        service=service,  # type: ignore[arg-type]
        refresh_seconds=999,
    )
    app = OtelPanelTestApp(panel)

    async with app.run_test() as pilot:
        await pilot.pause(0.2)

    metric_points = (
        panel.snapshot.summary["metric_points"] if panel.snapshot is not None else None
    )
    return service.calls, metric_points


def test_otel_panel_refresh_worker_applies_snapshot() -> None:
    calls, metric_points = asyncio.run(_mounted_otel_panel_snapshot())

    assert calls == 1
    assert metric_points == 0


def test_otel_panel_ignores_snapshot_when_not_composed() -> None:
    panel = OtelTelemetryPanel(
        infra=None,  # type: ignore[arg-type]
        bundle=DummyBundle(),  # type: ignore[arg-type]
        service=DummyService(telemetry=""),  # type: ignore[arg-type]
    )
    snapshot = _build_resource_snapshot("")

    panel._apply_snapshot(snapshot)

    assert panel.snapshot is snapshot


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
    assert snapshot.memory.total == pytest.approx(1000)
    assert snapshot.memory.used_ratio == pytest.approx(0.3)
    assert snapshot.memory.history == pytest.approx([0.3])
    assert snapshot.disk.used == pytest.approx(400)
    assert snapshot.disk.free == pytest.approx(600)
    assert snapshot.disk.total == pytest.approx(1000)
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
    assert snapshot.cpu.logical_cpus == 1


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


def test_resource_snapshot_memory_total_uses_available_when_present() -> None:
    telemetry = _jsonl(
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "system.memory.usage",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 4,
                                                "attributes": [_attr("state", "used")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 5,
                                                "attributes": [_attr("state", "cached")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 8,
                                                "attributes": [
                                                    _attr("state", "available")
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

    assert snapshot.memory.used == pytest.approx(4)
    assert snapshot.memory.free == pytest.approx(8)
    assert snapshot.memory.total == pytest.approx(12)
    assert snapshot.memory.used_ratio == pytest.approx(4 / 12)
    assert snapshot.memory.history == pytest.approx([4 / 12])


def test_resource_snapshot_memory_falls_back_to_free_plus_cache_states() -> None:
    telemetry = _jsonl(
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "system.memory.usage",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 4,
                                                "attributes": [_attr("state", "used")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 3,
                                                "attributes": [_attr("state", "free")],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 5,
                                                "attributes": [_attr("state", "cached")],
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

    assert snapshot.memory.used == pytest.approx(4)
    assert snapshot.memory.free == pytest.approx(3)
    assert snapshot.memory.total == pytest.approx(12)
    assert snapshot.memory.used_ratio == pytest.approx(4 / 12)


def test_resource_snapshot_disk_uses_root_mount_not_all_mounts() -> None:
    telemetry = _jsonl(
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "system.filesystem.usage",
                                    "unit": "By",
                                    "gauge": {
                                        "dataPoints": [
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 40,
                                                "attributes": [
                                                    _attr("mountpoint", "/"),
                                                    _attr("type", "ext4"),
                                                    _attr("state", "used"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 60,
                                                "attributes": [
                                                    _attr("mountpoint", "/"),
                                                    _attr("type", "ext4"),
                                                    _attr("state", "free"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 500,
                                                "attributes": [
                                                    _attr("mountpoint", "/mnt/data"),
                                                    _attr("type", "ext4"),
                                                    _attr("state", "used"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 500,
                                                "attributes": [
                                                    _attr("mountpoint", "/mnt/data"),
                                                    _attr("type", "ext4"),
                                                    _attr("state", "free"),
                                                ],
                                            },
                                            {
                                                "timeUnixNano": "61000000000",
                                                "asInt": 1000,
                                                "attributes": [
                                                    _attr("mountpoint", "/overlay"),
                                                    _attr("type", "overlay"),
                                                    _attr("state", "used"),
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

    assert snapshot.disk.used == pytest.approx(40)
    assert snapshot.disk.free == pytest.approx(60)
    assert snapshot.disk.total == pytest.approx(100)
    assert snapshot.disk.used_ratio == pytest.approx(0.4)
