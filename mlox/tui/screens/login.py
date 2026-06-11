"""Login screen for the Textual TUI."""

import os

from textual.app import ComposeResult
from textual.containers import CenterMiddle, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static


class LoginScreen(Screen):
    """Simple login screen that collects project and password."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, classes="app-header")
        with CenterMiddle(id="login-form"):
            yield Static("MLOX Login", id="login-title")
            yield Input(
                value=os.environ.get("MLOX_PROJECT_PATH") or os.environ.get("MLOX_PROJECT_NAME", "mlox.mlox"),
                placeholder="Project file",
                id="project",
            )
            yield Input(
                value=os.environ.get("MLOX_PROJECT_PASSWORD", ""),
                placeholder="Password",
                password=True,
                id="password",
            )
            with Horizontal(id="login-actions"):
                yield Button("Open", id="login-btn", variant="primary")
                yield Button("Create", id="create-btn")
            yield Static("", id="message")
        yield Footer(classes="app-footer")

    def on_button_pressed(
        self, event: Button.Pressed
    ) -> None:  # pragma: no cover - UI callback
        if event.button.id not in {"login-btn", "create-btn"}:
            return
        project = self.query_one("#project", Input).value.strip()
        password = self.query_one("#password", Input).value
        message = self.query_one("#message", Static)
        if not project or not password:
            message.update("Project and password are required")
            return

        login_fn = getattr(self.app, "login", None)
        if callable(login_fn) and login_fn(project, password, create=event.button.id == "create-btn"):
            self.app.push_screen("main")
        else:
            message.update(getattr(self.app, "login_error", None) or "Login failed")
