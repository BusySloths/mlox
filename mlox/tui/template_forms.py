"""Reusable Textual form specs for template setup flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
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


class TemplateSetupDialog(ModalScreen[FormValues | None]):
    """Modal prompt for collecting setup values for a template."""

    def __init__(self, spec: TemplateFormSpec) -> None:
        super().__init__()
        self.spec = spec

    def compose(self) -> ComposeResult:
        with Container(id="template-setup-dialog"):
            yield Label(self.spec.title, id="template-setup-title")
            yield Static(self.spec.description, id="template-setup-description")
            yield Static("", id="template-setup-error")
            with VerticalScroll(id="template-setup-fields"):
                for field_spec in self.spec.fields:
                    yield Label(field_spec.label, classes="template-field-label")
                    widget_id = self._field_id(field_spec.name)
                    if field_spec.kind == "select":
                        yield Select(
                            field_spec.options,
                            value=self._select_default(field_spec),
                            allow_blank=not field_spec.required,
                            id=widget_id,
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
                        yield Static(field_spec.help, classes="template-field-help")
            with Horizontal(id="template-setup-actions"):
                yield Button("Cancel", id="cancel-template-setup")
                yield Button(
                    self.spec.submit_label,
                    id="confirm-template-setup",
                    variant="success",
                )

    def on_mount(self) -> None:
        self.query_one("#template-setup-description", Static).display = bool(
            self.spec.description
        )
        first_field = self.spec.fields[0] if self.spec.fields else None
        if first_field:
            self.query_one(f"#{self._field_id(first_field.name)}").focus()

    @on(Input.Submitted)
    def handle_input_submitted(self, _: Input.Submitted) -> None:
        self._dismiss_with_values()

    @on(Button.Pressed, "#cancel-template-setup")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-template-setup")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_values()

    def _dismiss_with_values(self) -> None:
        values: FormValues = {}
        errors: list[str] = []
        for field_spec in self.spec.fields:
            value = self._read_field(field_spec)
            values[field_spec.name] = value
            errors.extend(self._validate_field(field_spec, value))

        if errors:
            self.query_one("#template-setup-error", Static).update("\n".join(errors))
            return

        self.dismiss(values)

    def _read_field(self, field_spec: TemplateFieldSpec) -> str:
        widget = self.query_one(f"#{self._field_id(field_spec.name)}")
        if isinstance(widget, Select):
            value = widget.value
            if value is Select.BLANK:
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

    def _select_default(self, field_spec: TemplateFieldSpec):
        option_values = {value for _, value in field_spec.options}
        if field_spec.default in option_values:
            return field_spec.default
        return Select.BLANK
