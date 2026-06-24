"""Bundle tag editing dialog."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection


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
