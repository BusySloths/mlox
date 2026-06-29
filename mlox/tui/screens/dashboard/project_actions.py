"""Actions available for the selected project root."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from .model import SelectionInfo


class RenameProjectDialog(ModalScreen[str | None]):
    """Modal prompt for changing the project display name."""

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Container(id="rename-project-dialog"):
            yield Label("Rename Project", id="rename-project-title")
            yield Input(
                value=self.current_name,
                placeholder="Project name",
                id="rename-project-name",
            )
            with Horizontal(id="rename-project-actions"):
                yield Button("Cancel", id="cancel-project-rename")
                yield Button(
                    "Rename",
                    id="confirm-project-rename",
                    variant="success",
                )

    def on_mount(self) -> None:
        self.query_one("#rename-project-name", Input).focus()

    @on(Input.Submitted, "#rename-project-name")
    def handle_name_submitted(self, _: Input.Submitted) -> None:
        self._dismiss_with_name()

    @on(Button.Pressed, "#cancel-project-rename")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-project-rename")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_name()

    def _dismiss_with_name(self) -> None:
        name = self.query_one("#rename-project-name", Input).value.strip()
        self.dismiss(name)


class ProjectActions(Container):
    """Root-selection actions for project-level operations."""

    class RenameRequested(Message):
        """Request that the dashboard opens the project rename modal."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        with Horizontal(id="project-action-content"):
            yield Button(
                "Rename Project",
                id="rename-project",
                variant="success",
            )
            yield Button(
                "Add Bundle from Server Template",
                id="add-bundle-from-server-template",
                variant="success",
            )

    def on_mount(self) -> None:
        self.border_title = "Project Actions"
        self.query_one("#add-bundle-from-server-template", Button).can_focus = False
        self._update_visibility(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        self._update_visibility(selection)

    def _update_visibility(self, selection: Optional[SelectionInfo]) -> None:
        self.display = bool(selection and selection.type == "root")

    @on(Button.Pressed, "#rename-project")
    def handle_rename_project(self, _: Button.Pressed) -> None:
        self.post_message(self.RenameRequested())
