"""Actions available for the selected infrastructure server."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Static

from mlox.application.use_cases.servers import (
    can_open_server_terminal,
    open_server_terminal,
)

from .model import SelectionInfo, is_bundle_initialized


class ServerActions(Container):
    """Selection-aware controls for bundle and server nodes."""

    class EditTagsRequested(Message):
        """Request that the dashboard opens the bundle tag editor."""

    class SetupBundleRequested(Message):
        """Request that the dashboard initializes the selected bundle."""

    class AddServiceRequested(Message):
        """Request that the dashboard opens service templates for the bundle."""

    class RemoveBundleRequested(Message):
        """Request that the dashboard removes the selected bundle."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._credentials_visible = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="server-action-buttons"):
            with Horizontal(id="server-primary-action-buttons"):
                yield Button("Open Terminal", id="open-server-terminal")
                yield Button("Show Credentials", id="toggle-server-credentials")
                yield Button("Refresh Server Info", id="refresh-runtime-info")
                yield Button("Setup Bundle", id="setup-bundle", variant="warning")
                yield Button("Add Service", id="add-service-to-bundle", variant="primary")
                yield Button("Edit Tags", id="edit-bundle-tags", variant="success")
            with Horizontal(id="server-destructive-action-buttons"):
                yield Button("Remove Bundle", id="remove-bundle", variant="error")
        yield Static(id="server-credentials")
        with Horizontal(id="credential-copy-buttons"):
            yield Button("Copy Password", id="copy-server-password")
            yield Button("Copy Passphrase", id="copy-server-passphrase")

    def on_mount(self) -> None:
        self._update_visibility(self.selection)
        self._render_title(self.selection)
        self._render_terminal_action(self.selection)
        self._render_credentials_action(self.selection)
        self._render_runtime_info_action(self.selection)
        self._render_bundle_lifecycle_actions(self.selection)
        self._render_add_service_action(self.selection)
        self._render_bundle_tag_action(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        self._credentials_visible = False
        self._update_visibility(selection)
        if self.is_mounted:
            self._render_title(selection)
            self._render_terminal_action(selection)
            self._render_credentials_action(selection)
            self._render_runtime_info_action(selection)
            self._render_bundle_lifecycle_actions(selection)
            self._render_add_service_action(selection)
            self._render_bundle_tag_action(selection)
            self.set_runtime_info_loading(False)
            self._render_credentials()

    def _update_visibility(self, selection: Optional[SelectionInfo]) -> None:
        self.display = bool(
            selection
            and selection.type in {"bundle", "server"}
            and (selection.server or getattr(selection.bundle, "server", None))
        )

    def _render_title(self, selection: Optional[SelectionInfo]) -> None:
        if selection and selection.type == "bundle":
            self.border_title = "Bundle Actions"
            return
        self.border_title = "Server Actions"

    def _render_terminal_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#open-server-terminal", Button)
        button.display = self.can_open_terminal(selection)

    def can_open_terminal(self, selection: Optional[SelectionInfo] = None) -> bool:
        selection = self.selection if selection is None else selection
        return bool(
            selection
            and selection.type == "server"
            and can_open_server_terminal(selection.server).success
        )

    def _render_credentials_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#toggle-server-credentials", Button)
        button.display = self.can_open_terminal(selection)

    def _render_runtime_info_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#refresh-runtime-info", Button)
        if selection and selection.type == "bundle":
            button.display = is_bundle_initialized(selection.bundle)
            button.label = "Refresh Backend Info"
            return
        button.display = bool(selection and selection.type == "server")
        button.label = "Refresh Server Info"

    def _render_bundle_lifecycle_actions(
        self, selection: Optional[SelectionInfo]
    ) -> None:
        setup = self.query_one("#setup-bundle", Button)
        remove = self.query_one("#remove-bundle", Button)
        is_bundle = bool(selection and selection.type == "bundle" and selection.bundle)
        setup.display = is_bundle and not is_bundle_initialized(selection.bundle)
        remove.display = is_bundle

    def _render_add_service_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#add-service-to-bundle", Button)
        button.display = bool(
            selection
            and selection.type == "bundle"
            and selection.bundle
            and is_bundle_initialized(selection.bundle)
        )

    def _render_bundle_tag_action(self, selection: Optional[SelectionInfo]) -> None:
        button = self.query_one("#edit-bundle-tags", Button)
        button.display = bool(selection and selection.type == "bundle")

    def _selected_server(self) -> object | None:
        selection = self.selection
        server = selection.server if selection else None
        if not server and selection:
            server = getattr(selection.bundle, "server", None)
        return server

    def _credential_values(self) -> tuple[str, str, str]:
        server = self._selected_server()
        mlox_user = getattr(server, "mlox_user", None)
        remote_user = getattr(server, "remote_user", None)
        return (
            str(getattr(mlox_user, "name", "") or ""),
            str(getattr(mlox_user, "pw", "") or ""),
            str(getattr(remote_user, "ssh_passphrase", "") or ""),
        )

    def _render_credentials(self) -> None:
        credentials = self.query_one("#server-credentials", Static)
        copy_buttons = self.query_one("#credential-copy-buttons", Horizontal)
        toggle = self.query_one("#toggle-server-credentials", Button)
        if not self.can_open_terminal():
            credentials.display = False
            copy_buttons.display = False
            toggle.label = "Show Credentials"
            return

        credentials.display = True
        if not self._credentials_visible:
            credentials.update("Credentials are hidden.")
            copy_buttons.display = False
            toggle.label = "Show Credentials"
            return

        username, password, passphrase = self._credential_values()
        credentials.update(
            "\n".join(
                [
                    f"SSH user: {username or 'not available'}",
                    f"mlox password: {password or 'not available'}",
                    f"SSH key passphrase: {passphrase or 'not available'}",
                ]
            )
        )
        copy_buttons.display = True
        self.query_one("#copy-server-password", Button).disabled = not bool(password)
        self.query_one("#copy-server-passphrase", Button).disabled = not bool(
            passphrase
        )
        toggle.label = "Hide Credentials"

    def set_runtime_info_loading(self, loading: bool) -> None:
        button = self.query_one("#refresh-runtime-info", Button)
        button.disabled = loading

    def set_bundle_lifecycle_loading(self, loading: bool) -> None:
        self.query_one("#setup-bundle", Button).disabled = loading
        self.query_one("#remove-bundle", Button).disabled = loading
        self.query_one("#add-service-to-bundle", Button).disabled = loading
        if not loading:
            self._render_bundle_lifecycle_actions(self.selection)
            self._render_add_service_action(self.selection)

    @on(Button.Pressed, "#open-server-terminal")
    def handle_open_terminal(self, _: Button.Pressed) -> None:
        self.open_terminal()

    def open_terminal(self) -> bool:
        """Open a terminal for the current selection when available."""

        server = self._selected_server()
        if not server or not self.can_open_terminal():
            return False

        result = open_server_terminal(server)
        if not result.success:
            self.notify(result.message, severity="error")
            return False

        self.notify(result.message)
        return True

    @on(Button.Pressed, "#toggle-server-credentials")
    def handle_toggle_credentials(self, _: Button.Pressed) -> None:
        self._credentials_visible = not self._credentials_visible
        self._render_credentials()

    @on(Button.Pressed, "#edit-bundle-tags")
    def handle_edit_bundle_tags(self, _: Button.Pressed) -> None:
        self.post_message(self.EditTagsRequested())

    @on(Button.Pressed, "#setup-bundle")
    def handle_setup_bundle(self, _: Button.Pressed) -> None:
        self.post_message(self.SetupBundleRequested())

    @on(Button.Pressed, "#add-service-to-bundle")
    def handle_add_service(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.AddServiceRequested())

    @on(Button.Pressed, "#remove-bundle")
    def handle_remove_bundle(self, _: Button.Pressed) -> None:
        self.post_message(self.RemoveBundleRequested())

    @on(Button.Pressed, "#copy-server-password")
    def handle_copy_password(self, _: Button.Pressed) -> None:
        _, password, _ = self._credential_values()
        if password:
            self.app.copy_to_clipboard(password)
            self.notify("Copied the mlox password.")

    @on(Button.Pressed, "#copy-server-passphrase")
    def handle_copy_passphrase(self, _: Button.Pressed) -> None:
        _, _, passphrase = self._credential_values()
        if passphrase:
            self.app.copy_to_clipboard(passphrase)
            self.notify("Copied the SSH key passphrase.")
