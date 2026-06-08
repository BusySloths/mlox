"""Actions available for the selected infrastructure server."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static

from mlox.terminal import TerminalLaunchError, launch_external_ssh_terminal

from .model import SelectionInfo


class ServerActions(Container):
    """Selection-aware controls for bundle and server nodes."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._credentials_visible = False

    def compose(self) -> ComposeResult:
        yield Static("Server Actions", classes="section-title")
        with Horizontal(id="server-action-buttons"):
            yield Button("Open Terminal", id="open-server-terminal")
            yield Button("Show Credentials", id="toggle-server-credentials")
        yield Static(id="server-credentials")
        with Horizontal(id="credential-copy-buttons"):
            yield Button("Copy Password", id="copy-server-password")
            yield Button("Copy Passphrase", id="copy-server-passphrase")

    def on_mount(self) -> None:
        self._update_visibility(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        self._credentials_visible = False
        self._update_visibility(selection)
        if self.is_mounted:
            self._render_credentials()

    def _update_visibility(self, selection: Optional[SelectionInfo]) -> None:
        self.display = bool(
            selection
            and selection.type in {"bundle", "server"}
            and (selection.server or getattr(selection.bundle, "server", None))
        )

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

    @on(Button.Pressed, "#open-server-terminal")
    def handle_open_terminal(self, _: Button.Pressed) -> None:
        self.open_terminal()

    def open_terminal(self) -> bool:
        """Open a terminal for the current selection when available."""

        server = self._selected_server()
        if not server:
            return False

        try:
            launch_external_ssh_terminal(server)
        except TerminalLaunchError as exc:
            self.notify(str(exc), severity="error")
            return False

        self.notify(f"Opened SSH terminal for {getattr(server, 'ip', 'server')}.")
        return True

    @on(Button.Pressed, "#toggle-server-credentials")
    def handle_toggle_credentials(self, _: Button.Pressed) -> None:
        self._credentials_visible = not self._credentials_visible
        self._render_credentials()

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
