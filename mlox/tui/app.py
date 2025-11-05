"""Application entry point for the Textual based TUI."""

from typing import Optional

from textual.app import App

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
