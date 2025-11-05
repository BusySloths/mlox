"""Login screen for the Textual TUI."""

import os

from textual.app import ComposeResult
from textual.containers import CenterMiddle
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static


class LoginScreen(Screen):
    """Simple login screen that collects project and password."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, classes="app-header")
        with CenterMiddle(id="login-form"):
            yield Static("MLOX Login", id="login-title")
            yield Input(
                value=os.environ.get("MLOX_PROJECT_NAME", "mlox"),
                placeholder="Project",
                id="project",
            )
            yield Input(
                value=os.environ.get("MLOX_PROJECT_PASSWORD", ""),
                placeholder="Password",
                password=True,
                id="password",
            )
            yield Button("Login", id="login-btn")
            yield Static("", id="message")
        yield Footer(classes="app-footer")

    def on_button_pressed(
        self, event: Button.Pressed
    ) -> None:  # pragma: no cover - UI callback
        if event.button.id != "login-btn":
            return
        project = self.query_one("#project", Input).value
        password = self.query_one("#password", Input).value
        login_fn = getattr(self.app, "login", None)
        if callable(login_fn) and login_fn(project, password):
            self.app.push_screen("main")
        else:
            self.query_one("#message", Static).update("Login failed")
