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
    valid_select_options,
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


async def _required_select_with_no_options_error() -> str:
    spec = TemplateFormSpec(
        title="Add Service",
        fields=[
            TemplateFieldSpec(
                "secret_manager",
                "Secret manager",
                kind="select",
                options=[],
            )
        ],
        materialize=lambda values, infra: values,
    )
    app = DialogHost(spec)
    async with app.run_test() as pilot:
        await pilot.pause()
        field = app.screen.query_one("#template-field-secret-manager", Input)
        assert field.value == ""
        assert field.disabled is True
        await pilot.click("#confirm-template-setup")
        await pilot.pause()
        error = app.screen.query_one("#template-setup-error", Static)
        return _render_text(error.render())


def test_template_setup_dialog_handles_required_select_without_options() -> None:
    error = asyncio.run(_required_select_with_no_options_error())

    assert "Secret manager is required." in error


async def _select_with_false_option_value() -> str:
    spec = TemplateFormSpec(
        title="Add Service",
        fields=[
            TemplateFieldSpec(
                "secret_manager",
                "Secret manager",
                kind="select",
                options=[("Broken manager", False), ("Valid manager", "manager-1")],
            )
        ],
        materialize=lambda values, infra: values,
    )
    app = DialogHost(spec)
    async with app.run_test() as pilot:
        await pilot.pause()
        select = app.screen.query_one("#template-field-secret-manager", Select)
        return str(select.value)


def test_template_setup_dialog_ignores_non_string_select_values() -> None:
    selected_value = asyncio.run(_select_with_false_option_value())

    assert selected_value == "manager-1"


def test_valid_select_options_keeps_string_values_only() -> None:
    field = TemplateFieldSpec(
        "manager",
        "Manager",
        kind="select",
        options=[("Empty", ""), ("Bad", False), ("Good", "manager-1")],
    )

    assert valid_select_options(field) == [
        ("Empty", ""),
        ("Good", "manager-1"),
    ]


async def _catalog_tls_visibility():
    from types import SimpleNamespace
    from mlox.tui.services.setup import catalog_app

    spec = catalog_app(None, None, SimpleNamespace(id="catalog-app-memos-0.31.0-docker", name="Memos"))
    app = DialogHost(spec)
    async with app.run_test() as pilot:
        await pilot.pause()
        mode = app.screen.query_one("#template-field-tls-mode", Select)
        host = app.screen.query_one("#template-field-hostname")
        secret = app.screen.query_one("#template-field-tls-secret-ref")
        assert not host.display and not secret.display
        mode.value = "letsencrypt"
        await pilot.pause()
        assert host.display and not secret.display
        await pilot.click("#confirm-template-setup")
        await pilot.pause()
        assert "Public hostname is required" in _render_text(app.screen.query_one("#template-setup-error", Static).render())
        mode.value = "managed"
        await pilot.pause()
        assert not host.display and secret.display
        app.screen._dismiss_with_values()
        await pilot.pause()
        assert "TLS secret (manager / name) is required" in _render_text(app.screen.query_one("#template-setup-error", Static).render())
        mode.value = "self-signed"
        await pilot.pause()
        assert not host.display and not secret.display


def test_catalog_tls_fields_follow_selected_mode():
    asyncio.run(_catalog_tls_visibility())
