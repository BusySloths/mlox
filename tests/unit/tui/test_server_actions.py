"""Server action widget tests."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import Button, Static

from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.screen import DashboardScreen
from mlox.tui.screens.dashboard.server_actions import ServerActions
from mlox.tui.screens.dashboard.server_info_panel import ServerInfoPanel


class ServerActionsTestApp(App):
    def compose(self) -> ComposeResult:
        yield ServerActions()


class DashboardServerInfoTestApp(App):
    def __init__(self) -> None:
        super().__init__()
        project = SimpleNamespace(
            name="test-project",
            infrastructure=SimpleNamespace(bundles=[]),
        )
        self.workspace = SimpleNamespace(
            name=project.name,
            infrastructure=project.infrastructure,
            path="test-project",
            active_secret_manager_name="Embedded Project Storage",
        )

    def compose(self) -> ComposeResult:
        yield DashboardScreen()


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
        "mlox.application.use_cases.servers.launch_external_ssh_terminal",
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
        "mlox.application.use_cases.servers.launch_external_ssh_terminal",
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
            self.workspace = SimpleNamespace(
                name=project.name,
                infrastructure=project.infrastructure,
            )

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


async def _server_action_button_presentation() -> list[str | None]:
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="server", server=SimpleNamespace())
        await pilot.pause()
        row = actions.query_one("#server-action-buttons")
        return [child.id for child in row.children]


def test_server_actions_keep_terminal_and_credentials_together() -> None:
    button_ids = asyncio.run(_server_action_button_presentation())

    assert button_ids == [
        "open-server-terminal",
        "toggle-server-credentials",
    ]


async def _action_titles_for_bundle_and_server() -> tuple[str, str]:
    server = SimpleNamespace(ip="10.0.0.5")
    bundle = SimpleNamespace(server=server)
    app = ServerActionsTestApp()
    async with app.run_test() as pilot:
        actions = app.query_one(ServerActions)
        actions.selection = SelectionInfo(type="bundle", bundle=bundle, server=server)
        await pilot.pause()
        bundle_title = str(actions.query_one("#server-actions-title", Static).render())

        actions.selection = SelectionInfo(type="server", server=server)
        await pilot.pause()
        server_title = str(actions.query_one("#server-actions-title", Static).render())
        return bundle_title, server_title


def test_actions_title_matches_bundle_or_server_selection() -> None:
    bundle_title, server_title = asyncio.run(_action_titles_for_bundle_and_server())

    assert bundle_title == "Bundle Actions"
    assert server_title == "Server Actions"


async def _server_info_refresh_button_presentation() -> tuple[str, str]:
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="server", server=SimpleNamespace())
        )
        await pilot.pause()
        button = app.query_one("#refresh-server-info", Button)
        return str(button.label), button.variant


def test_server_info_tab_has_refresh_button() -> None:
    label, variant = asyncio.run(_server_info_refresh_button_presentation())

    assert label == "Refresh"
    assert variant == "primary"


async def _click_server_info() -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {
            "cpu_count": 4,
            "host": "demo-host",
        },
        get_backend_status=lambda: {"backend.is_running": True},
    )

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = str(
                app.query_one(ServerInfoPanel)
                .query_one("#server-runtime-info", Static)
                .render()
            )
            if "demo-host" in rendered:
                return rendered
        return str(
            app.query_one(ServerInfoPanel)
            .query_one("#server-runtime-info", Static)
            .render()
        )


def test_server_info_panel_renders_server_information() -> None:
    rendered = asyncio.run(_click_server_info())

    assert "Server" in rendered
    assert "cpu_count: 4" in rendered
    assert "host: demo-host" in rendered
    assert "Backend" not in rendered
    assert "backend.is_running: True" not in rendered


async def _click_bundle_backend_info() -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {"host": "demo-host"},
        get_backend_status=lambda: {
            "backend.is_running": True,
            "k3s.is_running": True,
        },
    )
    bundle = SimpleNamespace(name="dev", server=server)

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = str(
                app.query_one(ServerInfoPanel)
                .query_one("#server-runtime-info", Static)
                .render()
            )
            if "backend.is_running" in rendered:
                return rendered
        return str(
            app.query_one(ServerInfoPanel)
            .query_one("#server-runtime-info", Static)
            .render()
        )


def test_bundle_info_panel_renders_backend_information() -> None:
    rendered = asyncio.run(_click_bundle_backend_info())

    assert "Backend" in rendered
    assert "backend.is_running: True" in rendered
    assert "k3s.is_running: True" in rendered
    assert "Server" not in rendered
    assert "host: demo-host" not in rendered


async def _click_server_info_with_blocked_worker() -> tuple[str, str]:
    release = threading.Event()

    def get_server_info(no_cache: bool = False) -> dict[str, str]:
        release.wait(timeout=2)
        return {"host": "demo-host"}

    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=get_server_info,
        get_backend_status=lambda: {"backend.is_running": True},
    )

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        await pilot.pause()
        loading = str(
            app.query_one(ServerInfoPanel)
            .query_one("#server-runtime-info", Static)
            .render()
        )
        release.set()
        for _ in range(20):
            await pilot.pause()
            rendered = str(
                app.query_one(ServerInfoPanel)
                .query_one("#server-runtime-info", Static)
                .render()
            )
            if "demo-host" in rendered:
                return loading, rendered
        return (
            loading,
            str(
                app.query_one(ServerInfoPanel)
                .query_one("#server-runtime-info", Static)
                .render()
            ),
        )


def test_server_info_button_loads_information_without_blocking_ui() -> None:
    loading, rendered = asyncio.run(_click_server_info_with_blocked_worker())

    assert "Loading server information..." in loading
    assert "host: demo-host" in rendered


async def _click_server_info_with_markup_like_output() -> str:
    server = SimpleNamespace(
        ip="10.0.0.5",
        get_server_info=lambda no_cache=True: {
            "message": "[not-a-rich-tag]literal[/not-a-rich-tag]",
        },
        get_backend_status=lambda: {"backend.is_running": True},
    )

    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        for _ in range(20):
            await pilot.pause()
            rendered = str(
                app.query_one(ServerInfoPanel)
                .query_one("#server-runtime-info", Static)
                .render()
            )
            if "not-a-rich-tag" in rendered:
                return rendered
        return str(
            app.query_one(ServerInfoPanel)
            .query_one("#server-runtime-info", Static)
            .render()
        )


def test_server_info_renders_markup_like_output_as_literal_text() -> None:
    rendered = asyncio.run(_click_server_info_with_markup_like_output())

    assert "[not-a-rich-tag]literal[/not-a-rich-tag]" in rendered


async def _server_info_uses_session_cache() -> tuple[str, str, int]:
    calls = 0

    def get_server_info(no_cache: bool = False) -> dict[str, str]:
        nonlocal calls
        if no_cache:
            calls += 1
        return {"host": "cached"}

    server = SimpleNamespace(
        get_server_info=get_server_info,
        get_backend_status=lambda: {},
    )
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info()
        for _ in range(20):
            await pilot.pause()
            first = str(
                app.query_one(ServerInfoPanel)
                .query_one("#server-runtime-info", Static)
                .render()
            )
            if "cached" in first:
                break

        app.query_one(ServerInfoPanel).load_selected_info()
        await pilot.pause()
        second = str(
            app.query_one(ServerInfoPanel)
            .query_one("#server-runtime-info", Static)
            .render()
        )
        return first, second, calls


def test_server_info_is_cached_for_current_tui_session() -> None:
    first, second, calls = asyncio.run(_server_info_uses_session_cache())

    assert "host: cached" in first
    assert "host: cached" in second
    assert calls == 1


async def _server_info_resets_on_selection_change() -> str:
    first_server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"host": "first"},
        get_backend_status=lambda: {},
    )
    second_server = SimpleNamespace(
        get_server_info=lambda no_cache=True: {"host": "second"},
        get_backend_status=lambda: {},
    )
    app = DashboardServerInfoTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="server", server=first_server))
        await pilot.pause()
        app.query_one(ServerInfoPanel).load_selected_info(refresh=True)
        await pilot.pause()

        screen._apply_selection(SelectionInfo(type="server", server=second_server))
        await pilot.pause()
        return str(
            app.query_one(ServerInfoPanel)
            .query_one("#server-runtime-info", Static)
            .render()
        )


def test_server_info_is_cleared_after_selection_changes() -> None:
    rendered = asyncio.run(_server_info_resets_on_selection_change())

    assert "first" not in rendered


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
