"""Overview panel tests."""

from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

from rich.console import Console
from textual.app import App, ComposeResult

from mlox.service import ServiceCapability
from mlox.server import ServerCapability
from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.overview_panel import OverviewPanel


def _render_panel(renderable) -> str:
    console = Console(file=io.StringIO(), record=True, width=120, height=40)
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


def test_bundle_overview_shows_firewall_summary_without_live_status() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    server = SimpleNamespace(
        ip="10.0.0.1",
        port=2222,
        state="running",
        backend=["docker"],
        capabilities={ServerCapability.FIREWALL},
    )
    service = SimpleNamespace(name="MLflow", service_ports={"http": 5000})

    panel.show_bundle(
        SelectionInfo(
            type="bundle",
            bundle=SimpleNamespace(
                name="demo",
                tags=[],
                services=[service],
                server=server,
            ),
            server=server,
        )
    )

    overview = _render_panel(rendered[0])

    assert "Firewall" in overview
    assert "Supported" in overview
    assert "2222, 5000" in overview


async def _project_overview_text() -> str:
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker"],
        capabilities={ServerCapability.DOCKER, ServerCapability.TERMINAL},
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
    assert "Bundle" in overview
    assert "Server" in overview
    assert "Backend" in overview
    assert "docker" in overview
    assert "terminal" not in overview
    assert "demo" in overview
    assert "10.0.0.1" in overview
    assert "running" in overview
    assert overview.count("Servers") == 1


async def _project_overview_with_service_states() -> str:
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker"],
        capabilities={ServerCapability.DOCKER, ServerCapability.TERMINAL},
        get_server_info=lambda: {"cpu_count": 8, "ram_gb": 16},
    )
    services = [
        SimpleNamespace(name="mlflow", service_config_id="template", state="running"),
        SimpleNamespace(
            name="airflow",
            service_config_id="template",
            state="un-initialized",
        ),
        SimpleNamespace(name="registry", service_config_id="template", state="failed"),
        SimpleNamespace(name="jobs", service_config_id="template", state="pending"),
    ]
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(
            bundles=[SimpleNamespace(name="demo", server=server, services=services)]
        )
    )
    app = OverviewTestApp(workspace)
    async with app.run_test() as pilot:
        panel = app.query_one(OverviewPanel)
        panel.show_infrastructure_overview()
        await pilot.pause()
        return _render_panel(panel.content)


def test_project_overview_shows_service_state_counts_per_server() -> None:
    overview = asyncio.run(_project_overview_with_service_states())

    assert "Service States" not in overview
    assert "Uninitialized" in overview
    assert "Running" in overview
    assert "Error" in overview
    assert "Other" in overview
    assert "Failed" not in overview
    assert "Pending" not in overview
    assert "Healthy" not in overview
    assert "Stopped" not in overview
    assert "running" in overview
    assert "4" in overview
    assert "mlflow" not in overview
    assert "airflow" not in overview
    assert "registry" not in overview


async def _project_overview_with_runtime_info_lookup() -> tuple[str, int]:
    calls = 0

    def count_if_called() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"cpu_count": 8, "ram_gb": 16}

    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker"],
        capabilities={ServerCapability.DOCKER},
        get_server_info=count_if_called,
    )
    workspace = SimpleNamespace(
        infrastructure=SimpleNamespace(
            bundles=[SimpleNamespace(name="demo", server=server, services=[])]
        )
    )
    app = OverviewTestApp(workspace)
    async with app.run_test() as pilot:
        panel = app.query_one(OverviewPanel)
        panel.show_infrastructure_overview()
        await pilot.pause()
        return _render_panel(panel.content), calls


def test_project_overview_calls_server_info_for_resource_totals() -> None:
    overview, calls = asyncio.run(_project_overview_with_runtime_info_lookup())

    assert "10.0.0.1" in overview
    assert "CPU Cores" in overview
    assert calls == 1


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

    assert "prod" in overview
    assert "gpu" in overview
    assert "critical" in overview
    assert "Service States" not in overview
    assert "Service Names" not in overview
    assert "running: 2, stopped: 1" not in overview


def test_empty_bundle_overview_points_to_service_templates() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    server = SimpleNamespace(ip="10.0.0.1", state="running", backend=["docker"])

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

    assert "No services installed yet" in overview
    assert "backend-specific services" in overview
    assert "Service Templates" in overview


def test_server_overview_shows_resource_info() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    server = SimpleNamespace(
        ip="10.0.0.1",
        state="running",
        backend=["docker"],
        capabilities={
            ServerCapability.DOCKER,
            ServerCapability.TERMINAL,
            ServerCapability.FIREWALL,
        },
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
    assert "Capabilities" in overview
    assert "docker" in overview
    assert "terminal" in overview
    assert "firewall" in overview


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
        capabilities={ServiceCapability.MODEL_REGISTRY, "dashboard"},
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
    assert "Capabilities" in overview
    assert "model registry" in overview
    assert "dashboard" in overview
    assert "Ports" in overview
    assert "http:5000" in overview


def test_service_overview_resolves_runtime_provider_connections() -> None:
    rendered = []
    panel = OverviewPanel()
    panel.update = rendered.append
    secret_provider = SimpleNamespace(
        uuid="secret-123",
        name="OpenBao",
        get_secret_manager_binding_label=lambda binding_id: (
            "runtime-Airflow-svc-123" if binding_id == "svc-123" else None
        ),
    )
    telemetry_provider = SimpleNamespace(uuid="otel-456", name="OpenTelemetry")
    secret_bundle = SimpleNamespace(server=SimpleNamespace(ip="10.0.0.2"))
    telemetry_bundle = SimpleNamespace(server=SimpleNamespace(ip="10.0.0.3"))
    providers = {
        secret_provider.uuid: secret_provider,
        telemetry_provider.uuid: telemetry_provider,
    }
    provider_bundles = {
        id(secret_provider): secret_bundle,
        id(telemetry_provider): telemetry_bundle,
    }
    lookup = SimpleNamespace(
        get_service_by_uuid=lambda service_uuid: providers.get(service_uuid),
        get_bundle_by_service=lambda provider: provider_bundles.get(id(provider)),
    )
    service = SimpleNamespace(
        name="Airflow",
        state="running",
        version="3.1",
        target_path="/opt/airflow",
        service_config_id="airflow",
        uuid="svc-123",
        secret_manager_uuid=secret_provider.uuid,
        telemetry_uuid=telemetry_provider.uuid,
        capabilities={
            ServiceCapability.SECRET_MANAGER_BINDING,
            ServiceCapability.TELEMETRY_BINDING,
        },
        service_ports={},
        compose_service_names={},
        service_urls={},
        _service_lookup=lookup,
    )
    bundle = SimpleNamespace(name="demo", server=SimpleNamespace(ip="10.0.0.1"))

    panel.show_service(
        SelectionInfo(type="service", bundle=bundle, service=service)
    )

    overview = _render_panel(rendered[0])

    assert "Secret Manager" in overview
    assert "OpenBao" in overview
    assert "secret-123" in overview
    assert "10.0.0.2" in overview
    assert "runtime-Airflow-svc-123" in overview
    assert "Telemetry" in overview
    assert "OpenTelemetry" in overview
    assert "otel-456" in overview
    assert "10.0.0.3" in overview

    service.secret_manager_uuid = None
    service.telemetry_uuid = None
    panel.show_service(
        SelectionInfo(type="service", bundle=bundle, service=service)
    )
    overview = _render_panel(rendered[-1])
    assert overview.count("Not connected") == 2
