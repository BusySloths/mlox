"""Application entry point for the Textual based TUI."""

import logging
from typing import Optional

from textual.app import App

from mlox.project import (
    InvalidProjectPasswordError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectStorageError,
    ProjectWorkspace,
)
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
        self.workspace: Optional[ProjectWorkspace] = None
        self.login_error: Optional[str] = None

    def on_mount(self) -> None:
        """Start the application on the login screen."""
        self.push_screen("login")

    def login(self, project: str, password: str, *, create: bool = False) -> bool:
        """Attempt to authenticate and load a project workspace."""

        self.login_error = None
        try:
            workspace = (
                ProjectWorkspace.create(project, password)
                if create
                else ProjectWorkspace.open(project, password)
            )
        except ProjectNotFoundError:
            self.login_error = "Project not found"
        except ProjectAlreadyExistsError:
            self.login_error = "Project already exists; use Open"
        except InvalidProjectPasswordError:
            self.login_error = "Invalid project password"
        except (ProjectStorageError, ValueError) as exc:
            self.login_error = str(exc)
        except Exception:
            logger.exception("Could not open MLOX project %s", project)
            self.login_error = "Could not load project"
        else:
            self.workspace = workspace
            return True
        return False


app = MLOXTextualApp()


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    app.run()
