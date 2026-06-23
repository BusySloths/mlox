"""Overview panel tests."""

from __future__ import annotations

import io
from types import SimpleNamespace

from rich.console import Console

from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.overview_panel import OverviewPanel


def _render_panel(renderable) -> str:
    console = Console(file=io.StringIO(), record=True, width=120)
    console.print(renderable)
    return console.export_text()


def test_bundle_overview_shows_backend() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker", "native"],
    )
    panel.show_bundle(
        SelectionInfo(
            type="bundle",
            bundle=SimpleNamespace(
                name="demo",
                tags=[],
                services=[],
                server=server,
            ),
            server=server,
        )
    )

    overview = _render_panel(rendered[0])

    assert "Backend" in overview
    assert "docker, native" in overview


def test_bundle_overview_shows_service_state_counts() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    server = SimpleNamespace(ip="10.0.0.1", state="running", backend=["docker"])
    services = [
        SimpleNamespace(name="MLflow", state="running"),
        SimpleNamespace(name="Postgres", state="running"),
        SimpleNamespace(name="Redis", state="stopped"),
    ]

    panel.show_bundle(
        SelectionInfo(
            type="bundle",
            bundle=SimpleNamespace(
                name="demo",
                tags=[],
                services=services,
                server=server,
            ),
            server=server,
        )
    )

    overview = _render_panel(rendered[0])

    assert "Service States" in overview
    assert "running: 2, stopped: 1" in overview


def test_server_overview_shows_resource_info() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker"],
        get_server_info=lambda: {
            "cpu_count": 8,
            "ram_gb": 16,
            "storage_gb": 200,
            "os": "Ubuntu",
            "kernel_version": "6.8",
            "uptime": "2 days",
        },
    )

    panel.show_server(SelectionInfo(type="server", server=server))

    overview = _render_panel(rendered[0])

    assert "Cpu Count" in overview
    assert "8" in overview
    assert "Ram Gb" in overview
    assert "16" in overview
    assert "Uptime" in overview
    assert "2 days" in overview


def test_service_overview_shows_version_ports_and_uuid() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    service = SimpleNamespace(
        name="MLflow",
        state="running",
        version="3.0",
        target_path="/opt/mlflow",
        service_config_id="mlflow",
        uuid="svc-123",
        service_ports={"http": 5000},
        compose_service_names={"app": "mlflow"},
        service_urls={},
    )
    bundle = SimpleNamespace(name="demo", server=SimpleNamespace(ip="10.0.0.1"))

    panel.show_service(
        SelectionInfo(type="service", bundle=bundle, service=service)
    )

    overview = _render_panel(rendered[0])

    assert "Version" in overview
    assert "3.0" in overview
    assert "UUID" in overview
    assert "svc-123" in overview
    assert "Ports" in overview
    assert "http:5000" in overview
