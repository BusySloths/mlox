"""Application entry point for the Textual based TUI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import sys

from textual.app import App

if __package__ in {None, ""}:  # pragma: no cover - handles execution via script path
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

from mlox.session import MloxSession

from mlox.tui.screens.login import LoginScreen
from mlox.tui.screens.dashboard import DashboardScreen


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
        self.session: Optional[MloxSession] = None

    def on_mount(self) -> None:
        """Start the application on the login screen."""
        self.push_screen("login")

    def login(self, project: str, password: str) -> bool:
        """Attempt to authenticate and load a project session."""

        try:
            session = MloxSession(project, password)
            if not session.secrets or session.secrets.is_working():
                self.session = session
                return True
        except Exception:
            pass
        return False


app = MLOXTextualApp()


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    app.run()
