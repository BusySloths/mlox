from __future__ import annotations

import asyncio
from types import SimpleNamespace
from textual.app import App
from textual.containers import Horizontal
from mlox.application.result import OperationResult
from mlox.tui.app import MLOXTextualApp
from mlox.tui.screens.login import LoginScreen


class LoginTestApp(App):
    def __init__(self):
        super().__init__()
        self.calls = []

    def on_mount(self):
        self.push_screen(LoginScreen())

    def login(self, project, password, *, create=False):
        self.calls.append((project, password, create))
        return False


async def _press_create():
    app = LoginTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#project").value = "demo.mlox"
        screen.query_one("#password").value = "pw"
        await pilot.click("#create-btn")
        await pilot.pause()
        return app.calls


def test_create_button_requests_explicit_project_creation():
    assert asyncio.run(_press_create()) == [("demo.mlox", "pw", True)]


async def _inspect_login_actions():
    app = LoginTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        actions = app.screen.query_one("#login-actions", Horizontal)
        return [button.id for button in actions.children]


def test_open_and_create_buttons_share_horizontal_action_row():
    assert asyncio.run(_inspect_login_actions()) == ["login-btn", "create-btn"]


async def _press_open_with_whitespace():
    app = LoginTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#project").value = "  demo  "
        screen.query_one("#password").value = "pw"
        await pilot.click("#login-btn")
        await pilot.pause()
        return app.calls


def test_open_normalizes_project_name():
    assert asyncio.run(_press_open_with_whitespace()) == [("demo", "pw", False)]


def test_textual_app_login_uses_project_application_use_case(monkeypatch) -> None:
    workspace = SimpleNamespace(name="demo")
    calls = []

    def open_workspace(project, password, *, create=False):
        calls.append((project, password, create))
        return OperationResult(True, 0, "opened", {"workspace": workspace})

    monkeypatch.setattr("mlox.tui.app.open_project_workspace", open_workspace)

    app = MLOXTextualApp()

    assert app.login("demo.mlox", "pw", create=True) is True
    assert app.workspace is workspace
    assert app.login_error is None
    assert calls == [("demo.mlox", "pw", True)]


def test_textual_app_login_reports_application_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "mlox.tui.app.open_project_workspace",
        lambda project, password, *, create=False: OperationResult(
            False,
            3,
            "Invalid project password",
        ),
    )

    app = MLOXTextualApp()

    assert app.login("demo.mlox", "wrong") is False
    assert app.workspace is None
    assert app.login_error == "Invalid project password"
