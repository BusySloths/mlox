"""Textual-based alternative UI for MLOX.

This module provides a simple terminal user interface using the
`textual` framework as an alternative to the Streamlit UI.  It offers a
basic login screen and a minimal set of pages that demonstrate how the
terminal UI could look.  The functionality is intentionally limited but
serves as a starting point for further development.
"""

from __future__ import annotations

import os
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, CenterMiddle
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Static,
    TabPane,
    TabbedContent,
)

from mlox.session import MloxSession


WELCOME_TEXT = """\
Accelerate your ML journey—deploy production-ready MLOps in minutes, not months.

MLOX helps individuals and small teams deploy, configure, and monitor full
MLOps stacks with minimal effort.
"""


class LoginScreen(Screen):
    """Simple login screen that collects project and password."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with CenterMiddle(id="login-form"):
            yield Static("MLOX Login", id="login-title")
            yield Input(
                value=os.environ.get("MLOX_CONFIG_USER", "mlox"),
                placeholder="Project",
                id="project",
            )
            yield Input(
                value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
                placeholder="Password",
                password=True,
                id="password",
            )
            yield Button("Login", id="login-btn")
            yield Static("", id="message")
        yield Footer()

    def on_button_pressed(
        self, event: Button.Pressed
    ) -> None:  # pragma: no cover - UI callback
        if event.button.id != "login-btn":
            return
        project = self.query_one("#project", Input).value
        password = self.query_one("#password", Input).value
        # Call the app's login method if available, then navigate to main screen
        login_fn = getattr(self.app, "login", None)
        if callable(login_fn) and login_fn(project, password):
            # Use push_screen for broader Textual compatibility
            self.app.push_screen("main")
        else:
            self.query_one("#message", Static).update("Login failed")


class MainScreen(Screen):
    """Main application screen shown after login."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield TabbedContent(
            TabPane("Home", Static(WELCOME_TEXT)),
            TabPane("Infrastructure", Static("Infrastructure view coming soon.")),
            TabPane("Services", Static("Services view coming soon.")),
        )
        yield Footer()


class MLOXTextualApp(App):
    """Main Textual application."""

    CSS_PATH = "tui.tcss"
    BINDINGS = [("q", "quit", "Quit")]
    SCREENS = {
        "login": LoginScreen,
        "main": MainScreen,
    }

    def __init__(self) -> None:
        super().__init__()
        self.session: Optional[MloxSession] = None

    def login(self, project: str, password: str) -> bool:
        try:
            ms = MloxSession(project, password)
            if ms.secrets.is_working():
                self.session = ms
                return True
        except Exception:
            pass
        return False

    def auto_login(self) -> bool:
        prj = os.environ.get("MLOX_PROJECT")
        pw = os.environ.get("MLOX_PASSWORD")
        if prj and pw:
            return self.login(prj, pw)
        return False

    def on_mount(self) -> None:  # pragma: no cover - UI lifecycle
        if self.auto_login():
            self.push_screen("main")
        else:
            self.push_screen("login")


def main() -> None:  # pragma: no cover - entry point
    MLOXTextualApp().run()


if __name__ == "__main__":  # pragma: no cover - script execution
    main()
