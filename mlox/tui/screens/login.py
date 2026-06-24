"""Login screen for the Textual TUI."""

import os

from textual.app import ComposeResult
from textual.containers import CenterMiddle, Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, LoadingIndicator, Static


MLOX_LOGO = r"""
,---.    ,---.  .---.       ,-----.     _____     __
|    \  /    |  | ,_|     .'  .-,  '.   \   _\   /  /
|  ,  \/  ,  |,-./  )    / ,-.|  \ _ \  .-./ ). /  '
|  |\_   /|  |\  '_ '`) ;  \  '_ /  | : \ '_ .') .'
|  _( )_/ |  | > (_)  ) |  _`,/ \ _/  |(_ (_) _) '
| (_ o _) |  |(  .  .-' : (  '\_/ \   ;  /    \   \
|  (_,_)  |  | `-'`-'|___\ `"/  \  ) /   `-'`-'    \
|  |      |  |  |        \'. \_/``".'   /  /   \    \
'--'      '--'  `--------`  '-----'    '--'     '----'
"""


class LoginScreen(Screen):
    """Simple login screen that collects project and password."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, classes="app-header")
        with CenterMiddle(id="login-shell"):
            with Container(id="login-form"):
                yield Static(MLOX_LOGO, id="login-logo")
                yield Static("Local MLOps workspace", id="login-subtitle")
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
                with Horizontal(id="login-loading-row"):
                    yield LoadingIndicator(id="login-loading-indicator")
                    yield Static("Loading project...", id="login-loading-label")
                yield Static("", id="message")
        yield Footer(classes="app-footer")

    def on_mount(self) -> None:
        self._set_loading(False)

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

        self._set_loading(True)
        message.update("")
        login_fn = getattr(self.app, "login", None)
        create = event.button.id == "create-btn"

        def load_project() -> None:
            success = bool(
                callable(login_fn) and login_fn(project, password, create=create)
            )
            self.app.call_from_thread(self._finish_login, success)

        self.app.run_worker(
            load_project,
            thread=True,
            exclusive=True,
            group="project-login",
        )

    def _finish_login(self, success: bool) -> None:
        if success:
            self.app.push_screen("main")
            return

        self._set_loading(False)
        message = self.query_one("#message", Static)
        message.update(getattr(self.app, "login_error", None) or "Login failed")

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#login-loading-row").display = loading
        for selector in ("#project", "#password", "#login-btn", "#create-btn"):
            self.query_one(selector).disabled = loading
