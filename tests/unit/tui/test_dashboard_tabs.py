"""Dashboard tab visibility tests."""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import TabbedContent

from mlox.tui.screens.dashboard.tree import InfraTree
from mlox.tui.screens.dashboard.app_log_panel import AppLogPanel
from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.screen import (
    DashboardScreen,
    LOGS_TAB_ID,
    SIDEBAR_DEFAULT_WIDTH,
    SIDEBAR_STEP,
    SERVER_TEMPLATES_TAB_ID,
    SERVICE_TEMPLATES_TAB_ID,
)


class DashboardTestApp(App):
    """Minimal app shell for mounting the dashboard."""

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


async def _visible_tabs_for(selection: SelectionInfo) -> tuple[str, str, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._update_template_tabs(selection)
        await pilot.pause()

        tabs = screen.query_one("#main-tabs", TabbedContent)
        server_tab = tabs.get_tab(SERVER_TEMPLATES_TAB_ID)
        service_tab = tabs.get_tab(SERVICE_TEMPLATES_TAB_ID)
        logs_tab = tabs.get_tab(LOGS_TAB_ID)
        return (
            server_tab.styles.display,
            service_tab.styles.display,
            logs_tab.styles.display,
        )


def test_root_selection_shows_only_server_templates_tab() -> None:
    server_display, service_display, logs_display = asyncio.run(
        _visible_tabs_for(SelectionInfo(type="root"))
    )

    assert server_display == "block"
    assert service_display == "none"
    assert logs_display == "none"


async def _root_label() -> str:
    app = DashboardTestApp()
    async with app.run_test():
        return app.query_one("#infra-tree").root.label.plain


def test_root_highlights_active_secret_manager() -> None:
    assert asyncio.run(_root_label()) == (
        "test-project  Secrets: Embedded Project Storage"
    )


async def _leaf_flags_for_server_and_services() -> tuple[bool, bool, bool]:
    app = DashboardTestApp()
    server = SimpleNamespace(ip="10.0.0.5")
    services = [SimpleNamespace(name="MLflow"), SimpleNamespace(name="Postgres")]
    bundle = SimpleNamespace(name="dev", server=server, services=services)
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    async with app.run_test():
        tree = app.query_one(InfraTree)
        bundle_node = tree.root.children[0]
        server_node = bundle_node.children[0]
        service_node = bundle_node.children[1]
        return (
            bundle_node.allow_expand,
            server_node.allow_expand,
            service_node.allow_expand,
        )


def test_server_and_service_tree_entries_are_leaf_nodes() -> None:
    bundle_allows_expand, server_allows_expand, service_allows_expand = asyncio.run(
        _leaf_flags_for_server_and_services()
    )

    assert bundle_allows_expand is True
    assert server_allows_expand is False
    assert service_allows_expand is False


def test_bundle_selection_shows_only_service_templates_tab() -> None:
    server_display, service_display, logs_display = asyncio.run(
        _visible_tabs_for(SelectionInfo(type="bundle"))
    )

    assert server_display == "none"
    assert service_display == "block"
    assert logs_display == "none"


def test_server_selection_hides_template_tabs() -> None:
    server_display, service_display, logs_display = asyncio.run(
        _visible_tabs_for(SelectionInfo(type="server"))
    )

    assert server_display == "none"
    assert service_display == "none"
    assert logs_display == "block"


def test_service_selection_shows_history_and_logs_tab() -> None:
    server_display, service_display, logs_display = asyncio.run(
        _visible_tabs_for(SelectionInfo(type="service"))
    )

    assert server_display == "none"
    assert service_display == "none"
    assert logs_display == "block"


async def _toggle_app_log_drawer() -> tuple[str, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        drawer = screen.query_one("#app-log-drawer", AppLogPanel)
        initial_display = drawer.styles.display

        await pilot.press("l")
        await pilot.pause()

        return initial_display, drawer.styles.display


def test_log_drawer_toggles_from_footer_binding() -> None:
    initial_display, toggled_display = asyncio.run(_toggle_app_log_drawer())

    assert initial_display == "none"
    assert toggled_display == "block"


async def _captured_app_log_lines() -> list[str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        drawer = app.query_one("#app-log-drawer", AppLogPanel)
        logging.getLogger("mlox.tui.test").warning("live drawer test message")
        await pilot.pause()
        return drawer._lines


def test_log_drawer_captures_live_logging_records() -> None:
    lines = asyncio.run(_captured_app_log_lines())

    assert any("live drawer test message" in line for line in lines)


async def _log_drawer_parent_type() -> str:
    app = DashboardTestApp()
    async with app.run_test():
        drawer = app.query_one("#app-log-drawer", AppLogPanel)
        return type(drawer.parent).__name__


def test_log_drawer_mounts_at_screen_level() -> None:
    parent_type = asyncio.run(_log_drawer_parent_type())

    assert parent_type == "DashboardScreen"


async def _sidebar_width_after_widening_with_binding() -> tuple[float, float]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        sidebar = screen.query_one("#sidebar", Container)

        initial_width = sidebar.styles.width.value
        await pilot.press("]")
        await pilot.pause()

        return initial_width, sidebar.styles.width.value


def test_sidebar_can_be_widened() -> None:
    initial_width, widened_width = asyncio.run(
        _sidebar_width_after_widening_with_binding()
    )

    assert initial_width == SIDEBAR_DEFAULT_WIDTH
    assert widened_width == SIDEBAR_DEFAULT_WIDTH + SIDEBAR_STEP


async def _reload_project_infrastructure(monkeypatch) -> tuple[str, object]:
    app = DashboardTestApp()

    def reload_project() -> None:
        app.workspace.name = "test-project-reloaded"
        app.workspace.infrastructure = SimpleNamespace(bundles=[])

    app.workspace.reload = reload_project
    async with app.run_test() as pilot:
        await pilot.press("R")
        deadline = time.monotonic() + 2
        while app.workspace.name == "test-project":
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for project reload.")
            await pilot.pause(0.05)

        screen = app.query_one(DashboardScreen)
        return (
            app.workspace.name,
            screen.query_one("#infra-tree").root.data,
        )


def test_reload_binding_reloads_project_infrastructure(monkeypatch) -> None:
    project_name, root_selection = asyncio.run(
        _reload_project_infrastructure(monkeypatch)
    )

    assert project_name == "test-project-reloaded"
    assert root_selection.type == "root"
