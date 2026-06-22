"""Application entry point for the Textual based TUI."""

import logging
from typing import Optional

from textual.app import App

from mlox.application.use_cases.project import open_project_workspace
from mlox.tui.screens.login import LoginScreen
from mlox.tui.screens.dashboard import DashboardScreen

logger = logging.getLogger(__name__)


class MLOXTextualApp(App):
    """Main Textual application for the terminal UI."""

    CSS_PATH = "tui.tcss"
    BINDINGS = [("q", "quit", "Quit")]
    SCREENS = {
        "login": LoginScreen,
        "main": DashboardScreen,
    }

    def __init__(self) -> None:
        super().__init__()
        self.workspace: Optional[object] = None
        self.login_error: Optional[str] = None

    def on_mount(self) -> None:
        """Start the application on the login screen."""
        self.push_screen("login")

    def login(self, project: str, password: str, *, create: bool = False) -> bool:
        """Attempt to authenticate and load a project workspace."""

        self.login_error = None
        try:
            result = open_project_workspace(project, password, create=create)
        except Exception:
            logger.exception("Could not open MLOX project %s", project)
            self.login_error = "Could not load project"
            return False
        if not result.success:
            self.login_error = result.message
            return False
        self.workspace = result.data["workspace"]
        return True


app = MLOXTextualApp()


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    app.run()
