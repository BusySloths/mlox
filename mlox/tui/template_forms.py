"""Reusable Textual form specs for template setup flows."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, TextArea

FieldKind = Literal["text", "password", "integer", "select", "multiline"]
FormValues = dict[str, str]
MaterializeParams = Callable[[FormValues, Any], dict[str, str]]


@dataclass
class TemplateFieldSpec:
    """One setup field in a reusable template form."""

    name: str
    label: str
    kind: FieldKind = "text"
    default: str = ""
    placeholder: str = ""
    required: bool = True
    help: str = ""
    min_value: int | None = None
    max_value: int | None = None
    options: list[tuple[str, str]] = field(default_factory=list)
    visible_when: tuple[str, str] | None = None
    options_loader: Callable[[], list[tuple[str, str]]] | None = None


@dataclass
class TemplateFormSpec:
    """A complete setup form plus parameter materialization."""

    title: str
    fields: list[TemplateFieldSpec]
    materialize: MaterializeParams
    description: str = ""
    submit_label: str = "Add Server"

    def params(self, values: FormValues, infra: Any) -> dict[str, str]:
        return self.materialize(values, infra)


def valid_select_options(field_spec: TemplateFieldSpec) -> list[tuple[str, str]]:
    """Return only Textual-safe select options for a field spec."""

    return [
        (str(label), value)
        for label, value in field_spec.options
        if isinstance(value, str)
    ]


class TemplateSetupForm(Container):
    """Reusable setup form that can be embedded in a template browser."""

    class BackRequested(Message):
        pass

    class Submitted(Message):
        def __init__(self, values: FormValues) -> None:
            super().__init__()
            self.values = values

    def __init__(self, spec: TemplateFormSpec) -> None:
        super().__init__()
        self.spec = spec
        self._loading_options: set[str] = set()
        self._loaded_options: set[str] = set()
        self._option_tasks: set[asyncio.Task] = set()

    def compose(self) -> ComposeResult:
        with Container(id="template-setup-dialog"):
            yield Label(self.spec.title, id="template-setup-title")
            yield Static(self.spec.description, id="template-setup-description")
            yield Static("", id="template-setup-error")
            with VerticalScroll(id="template-setup-fields"):
                for field_spec in self.spec.fields:
                    yield Label(field_spec.label, classes="template-field-label", id=f"{self._field_id(field_spec.name)}-label")
                    widget_id = self._field_id(field_spec.name)
                    if field_spec.kind == "select":
                        options = valid_select_options(field_spec)
                        if field_spec.options_loader:
                            yield Select(
                                options,
                                prompt="Loading options...",
                                allow_blank=True,
                                disabled=True,
                                id=widget_id,
                            )
                        elif options:
                            yield Select(
                                options,
                                value=self._select_default(field_spec, options),
                                allow_blank=not field_spec.required,
                                id=widget_id,
                            )
                        else:
                            yield Input(
                                value="",
                                placeholder="No options available",
                                id=widget_id,
                                disabled=True,
                            )
                    elif field_spec.kind == "multiline":
                        yield TextArea(
                            field_spec.default,
                            id=widget_id,
                            classes="template-field-multiline",
                        )
                    else:
                        yield Input(
                            value=field_spec.default,
                            placeholder=field_spec.placeholder,
                            password=field_spec.kind == "password",
                            type="integer" if field_spec.kind == "integer" else "text",
                            id=widget_id,
                        )
                    if field_spec.help:
                        yield Static(field_spec.help, classes="template-field-help", id=f"{widget_id}-help")
            with Horizontal(id="template-setup-actions"):
                yield Button("Back", id="cancel-template-setup")
                yield Button(
                    self.spec.submit_label,
                    id="confirm-template-setup",
                    variant="success",
                )

    def on_mount(self) -> None:
        self.query_one("#template-setup-description", Static).display = bool(
            self.spec.description
        )
        self._update_visibility()
        first_field = self.spec.fields[0] if self.spec.fields else None
        if first_field:
            self.query_one(f"#{self._field_id(first_field.name)}").focus()

    @on(Input.Submitted)
    def handle_input_submitted(self, _: Input.Submitted) -> None:
        self._dismiss_with_values()

    @on(Select.Changed)
    def handle_select_changed(self, event: Select.Changed) -> None:
        controllers = {
            self._field_id(field.visible_when[0])
            for field in self.spec.fields if field.visible_when
        }
        if event.select.id in controllers:
            self._update_visibility()

    def _update_visibility(self) -> None:
        fields = {field.name: field for field in self.spec.fields}
        for field in self.spec.fields:
            if not field.visible_when:
                continue
            controller, expected = field.visible_when
            visible = controller in fields and self._read_field(fields[controller]) == expected
            widget_id = self._field_id(field.name)
            for selector in (f"#{widget_id}", f"#{widget_id}-label"):
                widget = self.query_one(selector)
                if widget.display != visible:
                    widget.display = visible
            if field.help:
                help_widget = self.query_one(f"#{widget_id}-help")
                if help_widget.display != visible:
                    help_widget.display = visible
            if visible and field.options_loader and field.name not in self._loading_options and field.name not in self._loaded_options:
                self._loading_options.add(field.name)
                task = asyncio.create_task(self._load_options(field))
                self._option_tasks.add(task)
                task.add_done_callback(self._option_tasks.discard)

    async def _load_options(self, field: TemplateFieldSpec) -> None:
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def finish(value, error):
            if not future.done():
                if error is not None:
                    future.set_exception(error)
                else:
                    future.set_result(value)

        def load():
            try:
                value, error = field.options_loader(), None
            except Exception as exc:
                value, error = None, exc
            try:
                loop.call_soon_threadsafe(finish, value, error)
            except RuntimeError:
                pass  # The application was closed while the provider was busy.

        threading.Thread(target=load, daemon=True, name="mlox-template-options").start()
        try:
            options = await future
            options = [(str(label), value) for label, value in options if isinstance(value, str)]
            if not self.is_mounted:
                return
            select = self.query_one(f"#{self._field_id(field.name)}", Select)
            select.set_options(options)
            select.prompt = "Select a secret" if options else "No secrets available"
            select.disabled = not options
            self._loaded_options.add(field.name)
        except Exception:
            if self.is_mounted:
                select = self.query_one(f"#{self._field_id(field.name)}", Select)
                select.prompt = "Could not load options"
                select.disabled = True
        finally:
            self._loading_options.discard(field.name)

    def on_unmount(self) -> None:
        for task in self._option_tasks:
            task.cancel()

    @on(Button.Pressed, "#cancel-template-setup")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.post_message(self.BackRequested())

    @on(Button.Pressed, "#confirm-template-setup")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_values()

    def _dismiss_with_values(self) -> None:
        values: FormValues = {}
        errors: list[str] = []
        for field_spec in self.spec.fields:
            if field_spec.visible_when and not self.query_one(
                f"#{self._field_id(field_spec.name)}"
            ).display:
                values[field_spec.name] = ""
                continue
            value = self._read_field(field_spec)
            values[field_spec.name] = value
            errors.extend(self._validate_field(field_spec, value))

        if errors:
            self.query_one("#template-setup-error", Static).update("\n".join(errors))
            return

        self.post_message(self.Submitted(values))

    def _read_field(self, field_spec: TemplateFieldSpec) -> str:
        widget = self.query_one(f"#{self._field_id(field_spec.name)}")
        if isinstance(widget, Select):
            value = widget.value
            if value is Select.NULL:
                return ""
            return str(value)
        if isinstance(widget, TextArea):
            return widget.text
        if isinstance(widget, Input):
            return widget.value.strip()
        return ""

    def _validate_field(self, field_spec: TemplateFieldSpec, value: str) -> list[str]:
        errors: list[str] = []
        if field_spec.required and not value:
            errors.append(f"{field_spec.label} is required.")
            return errors
        if field_spec.kind == "integer" and value:
            try:
                number = int(value)
            except ValueError:
                return [f"{field_spec.label} must be a number."]
            if field_spec.min_value is not None and number < field_spec.min_value:
                errors.append(
                    f"{field_spec.label} must be at least {field_spec.min_value}."
                )
            if field_spec.max_value is not None and number > field_spec.max_value:
                errors.append(
                    f"{field_spec.label} must be at most {field_spec.max_value}."
                )
        return errors

    def _field_id(self, name: str) -> str:
        return f"template-field-{name.replace('_', '-')}"

    def _select_default(
        self,
        field_spec: TemplateFieldSpec,
        options: list[tuple[str, str]] | None = None,
    ):
        option_values = {
            value for _, value in (options or valid_select_options(field_spec))
        }
        if field_spec.default in option_values:
            return field_spec.default
        if field_spec.required and options:
            return options[0][1]
        return Select.NULL


class TemplateSetupDialog(ModalScreen[FormValues | None]):
    """Standalone wrapper for existing setup form callers."""

    def __init__(self, spec: TemplateFormSpec) -> None:
        super().__init__()
        self.spec = spec

    def compose(self) -> ComposeResult:
        yield TemplateSetupForm(self.spec)

    @on(TemplateSetupForm.BackRequested)
    def handle_back(self, message: TemplateSetupForm.BackRequested) -> None:
        message.stop()
        self.dismiss(None)

    @on(TemplateSetupForm.Submitted)
    def handle_submitted(self, message: TemplateSetupForm.Submitted) -> None:
        message.stop()
        self.dismiss(message.values)
