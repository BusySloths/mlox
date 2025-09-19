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
from textual.widgets import Button, Footer, Header, Input, Static, Tree

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
                tree: Tree = Tree("Infrastructure", id="infra-tree")
                tree.root.expand()
                yield tree
            with Container(id="content"):
                with Container(id="main-panel"):
                    yield Static(
                        "Select a server or service from the tree.",
                        id="selection-title",
                    )
                    yield Static(WELCOME_TEXT, id="home-content")
                with Container(id="detail-panel"):
                    yield Static("State: -", id="selection-state")
        yield Footer()

    def on_mount(self) -> None:
        self.populate_tree()
        self.update_selection_display(None)

    def populate_tree(self) -> None:
        """Populate tree with current infrastructure."""
        tree = self.query_one("#infra-tree", Tree)
        tree.root.label = "Infrastructure"
        tree.root.data = {"type": "root"}
        infra = getattr(getattr(self.app, "session", None), "infra", None)
        if not infra or len(infra.bundles) == 0:
            tree.root.add("No infrastructure available", data={"type": "empty"})
            tree.root.expand()
            return

        for bundle in infra.bundles:
            bundle_node = tree.root.add(
                f"Bundle: {bundle.name}", data={"type": "bundle", "bundle": bundle}
            )
            bundle_node.expand()
            server = bundle.server
            server_label = (
                f"Server: {getattr(server, 'ip', 'unknown')}"
                if server
                else "Server: unknown"
            )
            bundle_node.add(
                server_label,
                data={"type": "server", "bundle": bundle, "server": server},
            )
            if not bundle.services:
                bundle_node.add("No services", data={"type": "empty"})
                continue
            for svc in bundle.services:
                bundle_node.add(
                    f"Service: {svc.name}",
                    data={"type": "service", "bundle": bundle, "service": svc},
                )
        tree.root.expand()

    def update_selection_display(self, selection: Optional[dict]) -> None:
        """Update the detail panes based on the selected tree node."""

        title_widget = self.query_one("#selection-title", Static)
        state_widget = self.query_one("#selection-state", Static)
        description_widget = self.query_one("#home-content", Static)

        if not isinstance(selection, dict):
            title_widget.update("Select a server or service from the tree.")
            state_widget.update("State: -")
            description_widget.update(WELCOME_TEXT)
            return

        node_type = selection.get("type")
        if node_type == "service":
            service = selection.get("service")
            bundle = selection.get("bundle")
            if service and bundle:
                title_widget.update(f"{bundle.name}.{service.name}")
                state_widget.update(f"State: {getattr(service, 'state', 'unknown')}")
                server = getattr(bundle, "server", None)
                server_ip = getattr(server, "ip", "unknown") if server else "unknown"
                description_widget.update(
                    f"Bundle: {bundle.name}\nServer: {server_ip}\nService Path: {getattr(service, 'target_path', '-')}"
                )
                return
        elif node_type in {"server", "bundle"}:
            bundle = selection.get("bundle")
            server = selection.get("server")
            if bundle and server:
                server_ip = getattr(server, "ip", "unknown")
                title_widget.update(f"{bundle.name}.{server_ip}")
                state_widget.update(f"State: {getattr(server, 'state', 'unknown')}")
                description_widget.update(
                    f"Bundle: {bundle.name}\nServer IP: {server_ip}\nBackend: {', '.join(getattr(server, 'backend', []) or ['unknown'])}"
                )
                return

        title_widget.update("Select a server or service from the tree.")
        state_widget.update("State: -")
        description_widget.update(WELCOME_TEXT)

    def on_tree_node_selected(
        self, event: Tree.NodeSelected
    ) -> None:  # pragma: no cover - UI callback
        self.update_selection_display(event.node.data)


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
            if not ms.secrets or ms.secrets.is_working():
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
