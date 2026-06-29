"""Reusable template setup form tests."""

from __future__ import annotations

import asyncio

from rich.console import Console
from textual.app import App, ComposeResult
from textual.widgets import Input, Select, Static

from mlox.tui.template_forms import (
    TemplateFieldSpec,
    TemplateFormSpec,
    TemplateSetupDialog,
)


class DialogHost(App):
    def __init__(self, spec: TemplateFormSpec) -> None:
        super().__init__()
        self.spec = spec

    def compose(self) -> ComposeResult:
        yield Static("host")

    def on_mount(self) -> None:
        self.push_screen(TemplateSetupDialog(self.spec))


def _render_text(renderable: object) -> str:
    console = Console(record=True, width=100)
    console.print(renderable)
    return console.export_text()


async def _submit_invalid_integer() -> str:
    spec = TemplateFormSpec(
        title="Add Server",
        fields=[
            TemplateFieldSpec(
                "port",
                "SSH port",
                kind="integer",
                default="0",
                min_value=1,
                max_value=65535,
            )
        ],
        materialize=lambda values, infra: values,
    )
    app = DialogHost(spec)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#template-field-port", Input).value = "0"
        await pilot.click("#confirm-template-setup")
        await pilot.pause()
        error = app.screen.query_one("#template-setup-error", Static)
        return _render_text(error.render())


def test_template_setup_dialog_validates_integer_range() -> None:
    assert "SSH port must be at least 1." in asyncio.run(_submit_invalid_integer())


def test_template_form_spec_materializes_params() -> None:
    spec = TemplateFormSpec(
        title="Add Server",
        fields=[],
        materialize=lambda values, infra: {"${MLOX_IP}": values["host"]},
    )

    assert spec.params({"host": "127.0.0.1"}, object()) == {
        "${MLOX_IP}": "127.0.0.1"
    }


async def _optional_select_empty_default() -> str:
    spec = TemplateFormSpec(
        title="Add Server",
        fields=[
            TemplateFieldSpec(
                "controller",
                "Controller",
                kind="select",
                required=False,
                options=[("Create new cluster", ""), ("Join controller", "abc")],
                default="",
            )
        ],
        materialize=lambda values, infra: values,
    )
    app = DialogHost(spec)
    async with app.run_test() as pilot:
        await pilot.pause()
        select = app.screen.query_one("#template-field-controller", Select)
        return str(select.value)


def test_template_setup_dialog_allows_empty_string_select_default() -> None:
    assert asyncio.run(_optional_select_empty_default()) == ""
