"""Template panel tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult

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


async def _mounted_panel_detail_title(monkeypatch) -> tuple[int, str | None, str | None]:
    configs = [
        _fake_config("template-one", "Template One"),
        _fake_config("template-two", "Template Two"),
    ]
    monkeypatch.setattr(
        "mlox.tui.screens.dashboard.template_panel.load_all_server_configs",
        lambda: configs,
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
