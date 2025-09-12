"""Textual-based alternative UI for MLOX.

This module provides a simple terminal user interface using the
`textual` framework as an alternative to the Streamlit UI.  It offers a
basic login screen and a minimal set of pages that demonstrate how the
terminal UI could look.  The functionality is intentionally limited but
serves as a starting point for further development.
"""

import os
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import CenterMiddle, Container
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Static,
    TabPane,
    TabbedContent,
    Tree,
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
        with Container(id="main-area"):
            with Container(id="sidebar"):
                menu = Tree("Menu", id="menu-tree")
                menu.root.expand()
                menu.root.add("Home", id="tab-home")
                menu.root.add("Servers", id="tab-servers")
                menu.root.add("Services", id="tab-services")
                yield menu
            with Container(id="content"):
                with TabbedContent(id="tabs"):
                    with TabPane("Home", id="tab-home"):
                        yield Static(WELCOME_TEXT, id="home-content")
                    with TabPane("Servers", id="tab-servers"):
                        yield DataTable(id="servers-table")
                    with TabPane("Services", id="tab-services"):
                        yield DataTable(id="services-table")
        yield Footer()

    def on_mount(self) -> None:
        self.populate_tables()

    def populate_tables(self) -> None:
        """Populate tables with current infrastructure data."""
        servers = self.query_one("#servers-table", DataTable)
        services = self.query_one("#services-table", DataTable)
        servers.clear(columns=True)
        services.clear(columns=True)
        servers.add_columns("Name", "IP", "State")
        services.add_columns("Name", "Server", "State")
        infra = getattr(getattr(self.app, "session", None), "infra", None)
        if not infra or len(infra.bundles) == 0:
            servers.add_row("No servers", "-", "-")
            services.add_row("No services", "-", "-")
            return
        for bundle in infra.bundles:
            servers.add_row(bundle.name, bundle.server.ip, bundle.server.state)
            for svc in bundle.services:
                services.add_row(svc.name, bundle.server.ip, svc.state)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:  # pragma: no cover - UI callback
        tabbed = self.query_one(TabbedContent)
        tabbed.active = event.node.id


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
