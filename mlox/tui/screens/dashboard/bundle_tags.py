"""Bundle tag editing dialog."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection


class RenameBundleDialog(ModalScreen[str | None]):
    """Modal prompt for changing the bundle display name."""

    def __init__(self, current_name: str) -> None:
        super().__init__()
        self.current_name = current_name

    def compose(self) -> ComposeResult:
        with Container(id="rename-bundle-dialog"):
            yield Label("Rename Bundle", id="rename-bundle-title")
            yield Input(
                value=self.current_name,
                placeholder="Bundle name",
                id="rename-bundle-name",
            )
            with Horizontal(id="rename-bundle-actions"):
                yield Button("Cancel", id="cancel-bundle-rename")
                yield Button(
                    "Rename",
                    id="confirm-bundle-rename",
                    variant="success",
                )

    def on_mount(self) -> None:
        self.query_one("#rename-bundle-name", Input).focus()

    @on(Input.Submitted, "#rename-bundle-name")
    def handle_name_submitted(self, _: Input.Submitted) -> None:
        self._dismiss_with_name()

    @on(Button.Pressed, "#cancel-bundle-rename")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-bundle-rename")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_name()

    def _dismiss_with_name(self) -> None:
        name = self.query_one("#rename-bundle-name", Input).value.strip()
        self.dismiss(name)


class EditBundleTagsDialog(ModalScreen[list[str] | None]):
    """Modal prompt for selecting existing tags and adding new ones."""

    def __init__(
        self,
        *,
        bundle_name: str,
        current_tags: list[str],
        available_tags: list[str],
    ) -> None:
        super().__init__()
        self.bundle_name = bundle_name
        self.current_tags = current_tags
        self.available_tags = available_tags

    def compose(self) -> ComposeResult:
        current = {tag.casefold() for tag in self.current_tags}
        selections = [
            Selection(tag, tag, tag.casefold() in current)
            for tag in self.available_tags
        ]
        with Container(id="edit-bundle-tags-dialog"):
            yield Label(f"Edit Tags: {self.bundle_name}", id="edit-bundle-tags-title")
            yield Static(
                "Toggle existing tags and add new tags separated by commas.",
                id="edit-bundle-tags-help",
            )
            yield SelectionList(*selections, id="bundle-tag-selection")
            yield Input(
                placeholder="new-tag, another-tag",
                id="new-bundle-tags",
            )
            with Horizontal(id="edit-bundle-tags-actions"):
                yield Button("Cancel", id="cancel-bundle-tags")
                yield Button("Save Tags", id="confirm-bundle-tags", variant="success")

    def on_mount(self) -> None:
        selection = self.query_one("#bundle-tag-selection", SelectionList)
        selection.display = bool(self.available_tags)
        if self.available_tags:
            selection.focus()
            return
        self.query_one("#new-bundle-tags", Input).focus()

    @on(Input.Submitted, "#new-bundle-tags")
    def handle_new_tags_submitted(self, _: Input.Submitted) -> None:
        self._dismiss_with_tags()

    @on(Button.Pressed, "#cancel-bundle-tags")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-bundle-tags")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_tags()

    def _dismiss_with_tags(self) -> None:
        selection = self.query_one("#bundle-tag-selection", SelectionList)
        selected_tags = [str(tag) for tag in selection.selected]
        extra_tags = self.query_one("#new-bundle-tags", Input).value.split(",")
        self.dismiss(selected_tags + [str(tag) for tag in extra_tags])
