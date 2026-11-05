"""Template panel tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button, LoadingIndicator, Static, TextArea

from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.config import BuildConfig, ServiceConfig
from mlox.tui.screens.dashboard.template_panel import (
    TemplateBrowserDialog, TemplatePanel, TemplateSourceDialog,
)
from mlox.tui.template_forms import TemplateFieldSpec, TemplateFormSpec


class TemplatePanelTestApp(App):
    """Minimal app shell for mounting one template panel."""

    CSS_PATH = Path(__file__).resolve().parents[3] / "mlox/tui/tui.tcss"

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


def test_capability_pills_keep_labels_and_use_distinct_styles() -> None:
    panel = TemplatePanel(template_type="server")
    pills = panel._capability_pills({"backend": {"docker", "kubernetes"}, "server": ["health"]})
    assert "Backend" in pills.plain
    assert "docker" in pills.plain
    assert "kubernetes" in pills.plain
    assert "Server" in pills.plain
    assert "health" in pills.plain
    styles = [span.style for span in pills.spans if " on " in str(span.style)]
    assert len(set(styles)) == 3


def test_template_action_is_keyboard_accessible_and_disabled_when_empty(monkeypatch) -> None:
    async def exercise() -> None:
        configs = [_fake_config("template-one", "Template One")]
        monkeypatch.setattr(
            "mlox.application.use_cases.servers.load_all_server_configs",
            lambda include_plugins=True: configs,
        )
        app = TemplatePanelTestApp("server")
        async with app.run_test(size=(80, 24)) as pilot:
            panel = app.query_one(TemplatePanel)
            await pilot.pause()
            panel.table.focus()
            await pilot.press("tab", "tab")
            button = panel.query_one("#configure-add-server", Button)
            assert app.focused is button
            configs.clear()
            panel._show_templates()
            assert button.disabled
            assert panel.selected_config() is None

    asyncio.run(exercise())


def test_view_selected_template_source_is_read_only(monkeypatch, tmp_path) -> None:
    async def exercise() -> None:
        configs = [_fake_config("one", "One"), _fake_config("two", "Two")]
        (tmp_path / "Two.yaml").write_text("name: Two\nexample: true\n")
        monkeypatch.setattr(
            "mlox.application.use_cases.servers.load_all_server_configs",
            lambda include_plugins=True: configs,
        )
        monkeypatch.setattr(
            "mlox.tui.screens.dashboard.template_panel.get_stacks_path",
            lambda prefix: str(tmp_path),
        )
        app = TemplatePanelTestApp("server")
        async with app.run_test(size=(100, 30)) as pilot:
            panel = app.query_one(TemplatePanel)
            panel.table.focus()
            assert panel.table.region.right <= panel.details.region.x
            await pilot.press("down")
            await pilot.click("#view-template-source")
            dialog = app.screen
            assert isinstance(dialog, TemplateSourceDialog)
            source = dialog.query_one("#template-source-content", TextArea)
            assert source.read_only
            assert source.text == "name: Two\nexample: true\n"
            await pilot.press("escape")
            assert app.screen is not dialog

    asyncio.run(exercise())


def test_plugin_without_source_shows_generated_configuration(monkeypatch) -> None:
    async def exercise() -> None:
        config = ServiceConfig(
            id="plugin", name="Plugin", version="1", maintainer="Example",
            description="Example", description_short="Example", links={},
            build=BuildConfig(class_name="example.Plugin"),
        )
        monkeypatch.setattr(
            "mlox.application.use_cases.services.load_all_service_configs",
            lambda include_plugins=True: [config],
        )
        app = TemplatePanelTestApp("service")
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.click("#view-template-source")
            dialog = app.screen
            assert isinstance(dialog, TemplateSourceDialog)
            assert "Generated" in dialog.origin
            assert "id: plugin" in dialog.query_one("#template-source-content", TextArea).text

    asyncio.run(exercise())


def test_browser_navigation_preserves_selection_and_form_values(monkeypatch) -> None:
    async def exercise() -> None:
        configs = [_fake_config("one", "One"), _fake_config("two", "Two")]
        monkeypatch.setattr(
            "mlox.application.use_cases.servers.load_all_server_configs",
            lambda include_plugins=True: configs,
        )
        spec = TemplateFormSpec(
            title="Configure", fields=[TemplateFieldSpec("host", "Host")],
            materialize=lambda values, infra: values,
        )
        app = TemplatePanelTestApp("server")
        async with app.run_test(size=(80, 24)) as pilot:
            dialog = TemplateBrowserDialog("server", None, lambda config: spec)
            app.push_screen(dialog)
            await pilot.pause()
            actions = dialog.query_one("#template-action-row")
            close = dialog.query_one("#close-template-browser", Button)
            assert close.region.y == dialog.query_one("#configure-add-server", Button).region.y
            assert close.region.right == actions.content_region.right
            dialog.query_one(TemplatePanel).table.focus()
            await pilot.press("down")
            await pilot.click("#view-template-source")
            assert app.screen is dialog and dialog.view == "source"
            await pilot.press("escape")
            assert dialog.view == "browse"
            assert dialog.query_one(TemplatePanel).selected_config_id == "two"
            await pilot.click("#configure-add-server")
            assert app.screen is dialog and dialog.view == "form"
            form_frame = dialog.query_one("#template-browser-dialog")
            assert form_frame.region.height < dialog.size.height
            assert form_frame.region.contains_region(
                dialog.query_one("#confirm-template-setup", Button).region
            )
            dialog.query_one("#template-field-host").value = "example"
            await pilot.click("#cancel-template-setup")
            assert dialog.view == "browse"
            await pilot.click("#configure-add-server")
            assert dialog.query_one("#template-field-host").value == "example"
            await pilot.press("escape")
            assert dialog.view == "browse"
            await pilot.press("escape")
            assert app.screen is not dialog

    asyncio.run(exercise())


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
