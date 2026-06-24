"""Overview panel tests."""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

from rich.console import Console
from textual.app import App, ComposeResult

from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.overview_panel import OverviewPanel


def _render_panel(renderable) -> str:
    console = Console(file=io.StringIO(), record=True, width=120)
    console.print(renderable)
    return console.export_text()


class OverviewTestApp(App):
    def __init__(self, workspace) -> None:
        super().__init__()
        self.workspace = workspace

    def compose(self) -> ComposeResult:
        yield OverviewPanel()


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


async def _project_overview_text() -> str:
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker"],
        get_server_info=lambda: {"cpu_count": 8, "ram_gb": 16},
    )
    service = SimpleNamespace(
        name="MLflow",
        service_config_id="mlflow",
        state="running",
    )
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(
            bundles=[SimpleNamespace(name="demo", server=server, services=[service])]
        )
    )
    app = OverviewTestApp(workspace)
    async with app.run_test() as pilot:
        panel = app.query_one(OverviewPanel)
        panel.show_infrastructure_overview()
        await pilot.pause()
        return _render_panel(panel.content)


def test_project_overview_shows_backend_column_without_server_metric() -> None:
    overview = asyncio.run(_project_overview_text())

    assert "Bundles" in overview
    assert "Services" in overview
    assert "CPU Cores" in overview
    assert "RAM (GiB)" in overview
    assert "Servers" in overview
    assert "Backend" in overview
    assert "docker" in overview
    assert "10.0.0.1" in overview
    assert "running" in overview
    assert overview.count("Servers") == 1


def test_bundle_overview_shows_tags_without_repeating_services() -> None:
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
                tags=["prod", "gpu", "critical"],
                services=services,
                server=server,
            ),
            server=server,
        )
    )

    overview = _render_panel(rendered[0])

    assert "Tags" in overview
    assert "prod" in overview
    assert "gpu" in overview
    assert "critical" in overview
    assert "Service States" not in overview
    assert "Service Names" not in overview
    assert "running: 2, stopped: 1" not in overview


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
