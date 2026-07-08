"""Template panel tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button, LoadingIndicator, Static

from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.template_panel import TemplatePanel


class TemplatePanelTestApp(App):
    """Minimal app shell for mounting one template panel."""

    def __init__(self, template_type: str) -> None:
        super().__init__()
        self.template_type = template_type

    def compose(self) -> ComposeResult:
        yield TemplatePanel(template_type=self.template_type)


def _fake_config(config_id: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=config_id,
        name=name,
        version="1.0",
        maintainer="mlox",
        description="Long template description",
        description_short="Short description",
        requirements={"cpus": 2, "ram_gb": 4},
        ports={"http": 8080},
        capabilities={"server": ["docker"]},
        groups={"backend": {"docker": {}}},
        build=SimpleNamespace(class_name="mlox.example.Template", params={"x": "y"}),
        links={"docs": "https://example.invalid"},
        path=f"{name}.yaml",
    )


def _fake_service_config(
    config_id: str, name: str, backends: set[str]
) -> SimpleNamespace:
    config = _fake_config(config_id, name)
    config.backend_capabilities = lambda: backends
    return config


async def _mounted_panel_detail_title(monkeypatch) -> tuple[int, str | None, str | None]:
    configs = [
        _fake_config("template-one", "Template One"),
        _fake_config("template-two", "Template Two"),
    ]
    monkeypatch.setattr(
        "mlox.application.use_cases.servers.load_all_server_configs",
        lambda include_plugins=True: configs,
    )

    app = TemplatePanelTestApp("server")
    async with app.run_test() as pilot:
        panel = app.query_one(TemplatePanel)
        await pilot.pause()
        initial_config_id = panel.selected_config_id

        panel.table.focus()
        await pilot.press("down")
        await pilot.pause()

        return panel.table.row_count, initial_config_id, panel.selected_config_id


def test_template_panel_table_selection_updates_details(monkeypatch) -> None:
    row_count, initial_config_id, selected_config_id = asyncio.run(
        _mounted_panel_detail_title(monkeypatch)
    )

    assert row_count == 2
    assert initial_config_id == "template-one"
    assert selected_config_id == "template-two"


async def _server_template_action_state(monkeypatch) -> tuple[str, bool]:
    configs = [_fake_config("template-one", "Template One")]
    monkeypatch.setattr(
        "mlox.application.use_cases.servers.load_all_server_configs",
        lambda include_plugins=True: configs,
    )

    app = TemplatePanelTestApp("server")
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(TemplatePanel)
        button = panel.query_one("#configure-add-server", Button)
        return button.styles.display, button.disabled


def test_server_template_panel_shows_configure_action(monkeypatch) -> None:
    display, disabled = asyncio.run(_server_template_action_state(monkeypatch))

    assert display == "block"
    assert disabled is False


async def _service_template_action_state(monkeypatch) -> tuple[str, bool, str]:
    configs = [_fake_service_config("docker-service", "Docker Service", {"docker"})]
    monkeypatch.setattr(
        "mlox.application.use_cases.services.load_all_service_configs",
        lambda include_plugins=True: configs,
    )

    app = TemplatePanelTestApp("service")
    async with app.run_test() as pilot:
        panel = app.query_one(TemplatePanel)
        panel.selection = SelectionInfo(
            type="bundle",
            bundle=SimpleNamespace(server=SimpleNamespace(backend=["docker"])),
        )
        await pilot.pause()
        button = panel.query_one("#configure-add-server", Button)
        return button.styles.display, button.disabled, str(button.label)


def test_service_template_panel_shows_add_service_action(monkeypatch) -> None:
    display, disabled, label = asyncio.run(_service_template_action_state(monkeypatch))

    assert display == "block"
    assert disabled is False
    assert "Add Service" in label


async def _server_template_loading_state(monkeypatch) -> tuple[bool, bool]:
    configs = [_fake_config("template-one", "Template One")]
    monkeypatch.setattr(
        "mlox.application.use_cases.servers.load_all_server_configs",
        lambda include_plugins=True: configs,
    )

    app = TemplatePanelTestApp("server")
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(TemplatePanel)
        indicator = panel.query_one("#template-add-indicator", LoadingIndicator)
        status = panel.query_one("#template-add-status", Static)
        return indicator.display, status.display


def test_server_template_panel_does_not_show_add_spinner_initially(monkeypatch) -> None:
    indicator_display, status_display = asyncio.run(
        _server_template_loading_state(monkeypatch)
    )

    assert indicator_display is False
    assert status_display is False


async def _service_template_ids_for_bundle(monkeypatch) -> tuple[int, set[str]]:
    configs = [
        _fake_service_config("docker-service", "Docker Service", {"docker"}),
        _fake_service_config(
            "portable-service", "Portable Service", {"docker", "kubernetes"}
        ),
        _fake_service_config("k8s-service", "Kubernetes Service", {"kubernetes"}),
        _fake_service_config(
            "agent-service", "Agent Service", {"kubernetes_agent", "k3s_agent"}
        ),
    ]
    monkeypatch.setattr(
        "mlox.application.use_cases.services.load_all_service_configs",
        lambda include_plugins=True: configs,
    )

    app = TemplatePanelTestApp("service")
    async with app.run_test() as pilot:
        panel = app.query_one(TemplatePanel)
        panel.selection = SelectionInfo(
            type="bundle",
            bundle=SimpleNamespace(
                server=SimpleNamespace(backend=["docker", "native"])
            ),
        )
        await pilot.pause()
        return panel.table.row_count, set(panel._configs_by_key)


def test_service_templates_are_filtered_by_bundle_backend(monkeypatch) -> None:
    row_count, config_ids = asyncio.run(_service_template_ids_for_bundle(monkeypatch))

    assert row_count == 2
    assert config_ids == {"docker-service", "portable-service"}


async def _service_template_ids_for_agent_bundle(
    monkeypatch,
) -> tuple[int, set[str]]:
    configs = [
        _fake_service_config("k8s-service", "Kubernetes Service", {"kubernetes"}),
        _fake_service_config(
            "agent-service", "Agent Service", {"kubernetes_agent", "k3s_agent"}
        ),
    ]
    monkeypatch.setattr(
        "mlox.application.use_cases.services.load_all_service_configs",
        lambda include_plugins=True: configs,
    )

    app = TemplatePanelTestApp("service")
    async with app.run_test() as pilot:
        panel = app.query_one(TemplatePanel)
        panel.selection = SelectionInfo(
            type="bundle",
            bundle=SimpleNamespace(
                server=SimpleNamespace(backend=["kubernetes-agent", "k3s-agent"])
            ),
        )
        await pilot.pause()
        return panel.table.row_count, set(panel._configs_by_key)


def test_service_templates_match_normalized_agent_backends(monkeypatch) -> None:
    row_count, config_ids = asyncio.run(
        _service_template_ids_for_agent_bundle(monkeypatch)
    )

    assert row_count == 1
    assert config_ids == {"agent-service"}
