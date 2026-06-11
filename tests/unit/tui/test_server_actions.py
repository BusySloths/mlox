"""Server action widget tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Static

from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.server_actions import ServerActions


class ServerActionsTestApp(App):
    def compose(self) -> ComposeResult:
        yield ServerActions()


async def _visibility_for(selection: SelectionInfo) -> bool:
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = selection
        await pilot.pause()
        return actions.display


def test_actions_are_visible_for_bundle_and_server_selections() -> None:
    server = SimpleNamespace(ip="10.0.0.5")

    assert asyncio.run(
        _visibility_for(
            SelectionInfo(
                type="bundle",
                bundle=SimpleNamespace(server=server),
            )
        )
    )
    assert asyncio.run(
        _visibility_for(SelectionInfo(type="server", server=server))
    )


def test_actions_are_hidden_for_non_server_selections() -> None:
    assert not asyncio.run(_visibility_for(SelectionInfo(type="root")))
    assert not asyncio.run(
        _visibility_for(
            SelectionInfo(type="service", service=SimpleNamespace(name="service"))
        )
    )


async def _click_open_terminal(monkeypatch) -> list[object]:
    launched: list[object] = []
    monkeypatch.setattr(
        "mlox.tui.screens.dashboard.server_actions.launch_external_ssh_terminal",
        launched.append,
    )
    server = SimpleNamespace(ip="10.0.0.5")

    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=server)
        await pilot.pause()
        await pilot.click("#open-server-terminal")
        await pilot.pause()
    return launched


def test_open_terminal_button_launches_selected_server(monkeypatch) -> None:
    launched = asyncio.run(_click_open_terminal(monkeypatch))

    assert len(launched) == 1
    assert launched[0].ip == "10.0.0.5"


async def _open_terminal_with_binding(monkeypatch, selection) -> list[object]:
    launched: list[object] = []
    monkeypatch.setattr(
        "mlox.tui.screens.dashboard.server_actions.launch_external_ssh_terminal",
        launched.append,
    )

    from mlox.tui.screens.dashboard.screen import DashboardScreen

    class DashboardBindingTestApp(App):
        def __init__(self) -> None:
            super().__init__()
            project = SimpleNamespace(
                name="test-project",
                infrastructure=SimpleNamespace(bundles=[]),
            )
            session = SimpleNamespace(
                project=project,
                password="secret",
            )
            self.application = SimpleNamespace(project=project, session=session)

        def compose(self) -> ComposeResult:
            yield DashboardScreen()

    app = DashboardBindingTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(selection)
        await pilot.pause()
        await pilot.press("O")
        await pilot.pause()
    return launched


def test_open_terminal_binding_launches_for_server_selection(monkeypatch) -> None:
    server = SimpleNamespace(ip="10.0.0.5")

    launched = asyncio.run(
        _open_terminal_with_binding(
            monkeypatch,
            SelectionInfo(type="server", server=server),
        )
    )

    assert launched == [server]


def test_open_terminal_binding_does_nothing_for_root_selection(monkeypatch) -> None:
    launched = asyncio.run(
        _open_terminal_with_binding(
            monkeypatch,
            SelectionInfo(type="root"),
        )
    )

    assert launched == []


async def _reveal_credentials() -> tuple[str, str, str, str]:
    server = SimpleNamespace(
        ip="10.0.0.5",
        mlox_user=SimpleNamespace(name="mlox-user", pw="mlox-password"),
        remote_user=SimpleNamespace(ssh_passphrase="key-passphrase"),
    )
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=server)
        await pilot.pause()
        hidden = str(actions.query_one("#server-credentials", Static).render())

        await pilot.click("#toggle-server-credentials")
        await pilot.pause()
        revealed = str(actions.query_one("#server-credentials", Static).render())

        await pilot.click("#copy-server-password")
        password_clipboard = app.clipboard
        await pilot.click("#copy-server-passphrase")
        passphrase_clipboard = app.clipboard
        return hidden, revealed, password_clipboard, passphrase_clipboard


def test_credentials_are_hidden_then_revealed_and_copyable() -> None:
    hidden, revealed, password_clipboard, passphrase_clipboard = asyncio.run(
        _reveal_credentials()
    )

    assert "mlox-password" not in hidden
    assert "key-passphrase" not in hidden
    assert "mlox-user" in revealed
    assert "mlox-password" in revealed
    assert "key-passphrase" in revealed
    assert password_clipboard == "mlox-password"
    assert passphrase_clipboard == "key-passphrase"


async def _credentials_reset_on_selection_change() -> str:
    first_server = SimpleNamespace(
        mlox_user=SimpleNamespace(name="first", pw="first-password"),
        remote_user=SimpleNamespace(ssh_passphrase="first-passphrase"),
    )
    second_server = SimpleNamespace(
        mlox_user=SimpleNamespace(name="second", pw="second-password"),
        remote_user=SimpleNamespace(ssh_passphrase="second-passphrase"),
    )
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=first_server)
        await pilot.pause()
        await pilot.click("#toggle-server-credentials")
        await pilot.pause()

        actions.selection = SelectionInfo(type="server", server=second_server)
        await pilot.pause()
        return str(actions.query_one("#server-credentials", Static).render())


def test_credentials_are_hidden_after_selection_changes() -> None:
    rendered = asyncio.run(_credentials_reset_on_selection_change())

    assert "Credentials are hidden." in rendered
    assert "second-password" not in rendered
