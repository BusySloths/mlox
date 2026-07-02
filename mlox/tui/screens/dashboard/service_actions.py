"""Actions available for the selected infrastructure service."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from .model import SelectionInfo


class RenameServiceDialog(ModalScreen[str | None]):
    """Modal prompt for changing a service display name."""

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Container(id="rename-service-dialog"):
            yield Label("Rename Service", id="rename-service-title")
            yield Input(
                value=self.current_name,
                placeholder="Service name",
                id="rename-service-name",
            )
            with Horizontal(id="rename-service-actions"):
                yield Button("Cancel", id="cancel-service-rename")
                yield Button("Rename", id="confirm-service-rename", variant="success")

    def on_mount(self) -> None:
        self.query_one("#rename-service-name", Input).focus()

    @on(Input.Submitted, "#rename-service-name")
    def handle_name_submitted(self, _: Input.Submitted) -> None:
        self._dismiss_with_name()

    @on(Button.Pressed, "#cancel-service-rename")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-service-rename")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_name()

    def _dismiss_with_name(self) -> None:
        name = self.query_one("#rename-service-name", Input).value.strip()
        self.dismiss(name)


class RemoveServiceDialog(ModalScreen[bool]):
    """Confirmation prompt before tearing down and removing a service."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def compose(self) -> ComposeResult:
        with Container(id="remove-service-dialog"):
            yield Label("Remove Service", id="remove-service-title")
            yield Static(
                f"Do you really want to teardown and remove service '{self.service_name}'?",
                id="remove-service-message",
            )
            with Horizontal(id="remove-service-actions"):
                yield Button("Cancel", id="cancel-remove-service")
                yield Button(
                    "Teardown Service",
                    id="confirm-remove-service",
                    variant="error",
                )

    @on(Button.Pressed, "#cancel-remove-service")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm-remove-service")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)


class ServiceActions(Container):
    """Selection-aware controls for service nodes."""

    class RenameRequested(Message):
        """Request that the dashboard opens the service rename modal."""

    class TeardownRequested(Message):
        """Request that the dashboard confirms service teardown."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        with Horizontal(id="service-action-buttons"):
            with Horizontal(id="service-primary-action-buttons"):
                yield Button("Rename Service", id="rename-service", variant="success")
            with Horizontal(id="service-destructive-action-buttons"):
                yield Button("Teardown Service", id="teardown-service", variant="error")

    def on_mount(self) -> None:
        self.border_title = "Service Actions"
        self._update_visibility(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        self._update_visibility(selection)
        if self.is_mounted:
            self.set_loading(False)

    def _update_visibility(self, selection: Optional[SelectionInfo]) -> None:
        self.display = bool(selection and selection.type == "service" and selection.service)

    def set_loading(self, loading: bool) -> None:
        rename = self.query_one("#rename-service", Button)
        teardown = self.query_one("#teardown-service", Button)
        rename.disabled = loading
        teardown.disabled = loading
        teardown.label = "Tearing down..." if loading else "Teardown Service"

    @on(Button.Pressed, "#rename-service")
    def handle_rename(self, _: Button.Pressed) -> None:
        self.post_message(self.RenameRequested())

    @on(Button.Pressed, "#teardown-service")
    def handle_teardown(self, _: Button.Pressed) -> None:
        self.post_message(self.TeardownRequested())
