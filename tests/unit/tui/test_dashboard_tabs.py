"""Dashboard tab visibility tests."""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from types import SimpleNamespace

from rich.console import Console
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Input, SelectionList, Static, TabbedContent, TextArea

from mlox.application.result import OperationResult
from mlox.tui.screens.dashboard.overview_panel import OverviewPanel
from mlox.tui.screens.dashboard.project_actions import ProjectActions
from mlox.tui.screens.dashboard.server_actions import ServerActions
from mlox.tui.screens.dashboard.service_actions import ServiceActions
from mlox.tui.screens.dashboard.secret_manager_panel import SecretManagerPanel
from mlox.tui.screens.dashboard.template_panel import TemplatePanel
from mlox.tui.screens.dashboard.tree import InfraTree
from mlox.tui.screens.dashboard.app_log_panel import AppLogPanel
from mlox.tui.screens.dashboard.model import SelectionInfo
from mlox.tui.screens.dashboard.screen import (
    DashboardScreen,
    FIREWALL_TAB_ID,
    LOGS_TAB_ID,
    MODELS_TAB_ID,
    MONITOR_TAB_ID,
    SECRET_MANAGER_TAB_ID,
    SIDEBAR_DEFAULT_WIDTH,
    SIDEBAR_STEP,
    SERVER_TEMPLATES_TAB_ID,
    SERVICE_TEMPLATES_TAB_ID,
)
from mlox.tui.template_forms import TemplateFieldSpec, TemplateFormSpec


class DashboardTestApp(App):
    """Minimal app shell for mounting the dashboard."""

    def __init__(self) -> None:
        super().__init__()
        self.commits = []
        self.copied_text = ""
        self.secret_store = {
            "api-token": "secret-value",
            "db-password": {"password": "secret-value"},
        }
        self.service_secret_store = {"service-token": "service-secret-value"}

        class SecretManager:
            supports_keyfile_export = False

            def __init__(self, store):
                self.store = store

            def is_working(self):
                return True

            def list_secrets(self, keys_only=False):
                assert keys_only is True
                return {name: None for name in self.store}

            def load_secret(self, name):
                return self.store.get(name)

            def save_secret(self, name, value):
                self.store[name] = value

        embedded_manager = SecretManager(self.secret_store)
        service_manager = SecretManager(self.service_secret_store)
        service = SimpleNamespace(uuid="service-secret-manager", name="External Vault")
        server = SimpleNamespace(backend=["docker"])
        bundle = SimpleNamespace(name="vault-bundle", server=server, services=[service])
        service.bundle = bundle
        descriptors = {
            "embedded": SimpleNamespace(
                id="embedded",
                name="Embedded Project Storage",
                kind="embedded",
                service_uuid=None,
                is_active=True,
                is_available=True,
                supports_keyfile_export=False,
                manager=embedded_manager,
                service=None,
            ),
            service.uuid: SimpleNamespace(
                id=service.uuid,
                name=service.name,
                kind="service",
                service_uuid=service.uuid,
                is_active=False,
                is_available=None,
                supports_keyfile_export=False,
                manager=None,
                service=service,
            ),
        }
        probed_descriptors = {
            **descriptors,
            service.uuid: SimpleNamespace(
                id=service.uuid,
                name=service.name,
                kind="service",
                service_uuid=service.uuid,
                is_active=False,
                is_available=True,
                supports_keyfile_export=False,
                manager=service_manager,
                service=service,
            ),
        }

        project = SimpleNamespace(
            name="test-project",
            infrastructure=SimpleNamespace(bundles=[]),
        )

        def commit() -> None:
            self.commits.append(self.workspace.name)

        def set_secret_manager(manager_id: str):
            descriptors["embedded"].is_active = False
            probed_descriptors["embedded"].is_active = False
            descriptors[manager_id].is_active = True
            descriptors[manager_id].is_available = True
            probed_descriptors[manager_id].is_active = True
            probed_descriptors[manager_id].is_available = True
            self.workspace.active_secret_manager_name = descriptors[manager_id].name
            self.workspace.secret_manager_kind = "service"
            return OperationResult(True, 0, "Active secret manager updated.")

        def use_embedded_secret_manager():
            descriptors["embedded"].is_active = True
            probed_descriptors["embedded"].is_active = True
            descriptors[service.uuid].is_active = False
            probed_descriptors[service.uuid].is_active = False
            self.workspace.active_secret_manager_name = "Embedded Project Storage"
            self.workspace.secret_manager_kind = "embedded"
            return OperationResult(True, 0, "Active secret manager updated.")

        self.workspace = SimpleNamespace(
            name=project.name,
            infrastructure=project.infrastructure,
            path="test-project",
            active_secret_manager_name="Embedded Project Storage",
            secret_manager_kind="embedded",
            secrets=embedded_manager,
            list_secret_managers=lambda: list(descriptors.values()),
            probe_secret_manager=lambda manager_id: probed_descriptors[manager_id],
            set_secret_manager=set_secret_manager,
            use_embedded_secret_manager=use_embedded_secret_manager,
            commit=commit,
        )

    def compose(self) -> ComposeResult:
        yield DashboardScreen()

    def copy_to_clipboard(self, text: str) -> None:
        self.copied_text = text


def _render_text(renderable: object) -> str:
    console = Console(file=io.StringIO(), record=True, width=120)
    console.print(renderable)
    return console.export_text()


def _secret_detail_text(panel: SecretManagerPanel) -> str:
    if panel.detail_editor.display:
        return f"{panel.detail_editor.border_title}\n{panel.detail_editor.text}"
    return _render_text(panel.detail.content)


async def _visible_tabs_for(
    selection: SelectionInfo,
) -> tuple[str, str, str, str, str, str, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._update_template_tabs(selection)
        await pilot.pause()

        tabs = screen.query_one("#main-tabs", TabbedContent)
        server_tab = tabs.get_tab(SERVER_TEMPLATES_TAB_ID)
        secret_tab = tabs.get_tab(SECRET_MANAGER_TAB_ID)
        firewall_tab = tabs.get_tab(FIREWALL_TAB_ID)
        monitor_tab = tabs.get_tab(MONITOR_TAB_ID)
        models_tab = tabs.get_tab(MODELS_TAB_ID)
        service_tab = tabs.get_tab(SERVICE_TEMPLATES_TAB_ID)
        logs_tab = tabs.get_tab(LOGS_TAB_ID)
        return (
            server_tab.styles.display,
            secret_tab.styles.display,
            firewall_tab.styles.display,
            monitor_tab.styles.display,
            models_tab.styles.display,
            service_tab.styles.display,
            logs_tab.styles.display,
        )


def test_root_selection_shows_project_tabs() -> None:
    (
        server_display,
        secret_display,
        firewall_display,
        monitor_display,
        models_display,
        service_display,
        logs_display,
    ) = asyncio.run(
        _visible_tabs_for(SelectionInfo(type="root"))
    )

    assert server_display == "block"
    assert secret_display == "block"
    assert firewall_display == "block"
    assert monitor_display == "block"
    assert models_display == "block"
    assert service_display == "none"
    assert logs_display == "none"


async def _copy_model_example_with_keybinding() -> str:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        tabs = app.query_one("#main-tabs", TabbedContent)
        tabs.active = MODELS_TAB_ID
        panel = app.query_one("#models-panel")
        panel.example.text = "curl -k https://endpoint/invocations"
        await pilot.press("c")
        await pilot.pause()
        return app.copied_text


def test_models_tab_copy_keybinding_copies_current_curl_example() -> None:
    clipboard = asyncio.run(_copy_model_example_with_keybinding())

    assert clipboard == "curl -k https://endpoint/invocations"


async def _model_selection_example_prompt() -> str:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        panel = app.query_one("#models-panel")
        panel._endpoints = [{"id": "endpoint-1", "registry_id": "registry-1"}]
        panel._models_by_endpoint = {
            "endpoint-1": [
                {
                    "name": "Demo",
                    "version": "1",
                    "type": "MLServer",
                    "status": "running",
                }
            ]
        }
        panel._select_endpoint("endpoint-1")
        return panel.example.text


def test_models_tab_selection_prompts_before_loading_example() -> None:
    text = asyncio.run(_model_selection_example_prompt())

    assert "Press Load Curl Example" in text
    assert not text.startswith("curl")


async def _models_metric_text() -> str:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        panel = app.query_one("#models-panel")
        panel._registries = [{"id": "registry-1"}]
        panel._endpoints = [{"id": "endpoint-1"}, {"id": "endpoint-2"}]
        panel._models_by_endpoint = {
            "endpoint-1": [
                {"name": "Ready", "status": "READY"},
                {"name": "Failed", "status": "error"},
            ],
            "endpoint-2": [{"name": "Running", "status": "running"}],
        }
        panel._update_metrics(panel._model_metrics())
        return "\n".join(
            _render_text(app.query_one(selector).content)
            for selector in (
                "#models-metric-registries",
                "#models-metric-endpoints",
                "#models-metric-total",
                "#models-metric-available",
            )
        )


def test_models_tab_shows_top_metric_cards() -> None:
    text = asyncio.run(_models_metric_text())

    assert "Registries" in text
    assert "Endpoints" in text
    assert "Models Total" in text
    assert "Models Available" in text
    assert "1" in text
    assert "2" in text
    assert "3" in text


async def _monitor_table_text() -> str:
    app = DashboardTestApp()
    monitor_service = SimpleNamespace(
        name="otel",
        state="running",
        capabilities={"monitor"},
        get_monitor_snapshot=lambda bundle: {
            "cpu_used_ratio": 0.42,
            "ram_free_ratio": 0.73,
            "disk_free_ratio": 0.81,
            "network_in_rate": 2048,
            "network_out_rate": 1024,
            "network_unit": "By",
            "metric_points": 9,
        },
    )
    bundle = SimpleNamespace(
        name="prod",
        server=SimpleNamespace(ip="10.0.0.5"),
        services=[monitor_service],
    )
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="root"))
        tabs = screen.query_one("#main-tabs", TabbedContent)
        tabs.active = MONITOR_TAB_ID
        table = app.query_one("#monitor-table")
        deadline = time.monotonic() + 2
        while table.row_count == 0:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for monitor rows.")
            await pilot.pause(0.05)
        return " ".join(str(cell) for cell in table.get_row_at(0))


def test_monitor_tab_shows_project_monitor_table() -> None:
    text = asyncio.run(_monitor_table_text())

    assert "prod" in text
    assert "10.0.0.5" in text
    assert "otel" in text
    assert "42.0%" in text
    assert "73.0%" in text
    assert "2.0 KB/s" in text


async def _monitor_detail_text() -> str:
    app = DashboardTestApp()
    monitor_service = SimpleNamespace(
        name="otel",
        state="running",
        capabilities={"monitor"},
        get_monitor_snapshot=lambda bundle: {
            "cpu_used_ratio": 0.42,
            "ram_free_ratio": 0.73,
            "disk_free_ratio": 0.81,
            "metric_points": 9,
        },
    )
    bundle = SimpleNamespace(
        name="prod",
        server=SimpleNamespace(ip="10.0.0.5"),
        services=[monitor_service],
    )
    config = SimpleNamespace(
        get_ui_handler=lambda ui, handler: (
            lambda infra, bundle_arg, service_arg: Static("Detailed monitor settings")
        )
    )
    app.workspace.infrastructure = SimpleNamespace(
        bundles=[bundle],
        get_service_config=lambda service: config,
    )

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(SelectionInfo(type="root"))
        screen.query_one("#main-tabs", TabbedContent).active = MONITOR_TAB_ID
        detail = app.query_one("#monitor-service-detail")
        deadline = time.monotonic() + 2
        text = ""
        while "Detailed monitor settings" not in text:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for monitor detail.")
            await pilot.pause(0.05)
            if detail.children:
                text = _render_text(detail.children[0].content)
        return text


def test_monitor_tab_shows_selected_service_settings_below_table() -> None:
    text = asyncio.run(_monitor_detail_text())

    assert "Detailed monitor settings" in text


async def _secret_manager_panel_text() -> str:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SecretManagerPanel)
        deadline = time.monotonic() + 2
        while panel.table.row_count == 0:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for secret-manager panel.")
            await pilot.pause(0.05)
        rows = [
            " ".join(str(cell) for cell in panel.table.get_row_at(index))
            for index in range(panel.table.row_count)
        ]
        manager_rows = [
            " ".join(str(cell) for cell in panel.manager_table.get_row_at(index))
            for index in range(panel.manager_table.row_count)
        ]
        return "\n".join(
            [
                _render_text(panel.summary.content),
                "\n".join(manager_rows),
                "\n".join(rows),
                _render_text(panel.detail.content),
            ]
        )


def test_secret_manager_tab_renders_redacted_secret_inventory() -> None:
    rendered = asyncio.run(_secret_manager_panel_text())

    assert "Embedded Project Storage" in rendered
    assert "External Vault" in rendered
    assert "api-token" in rendered
    assert "db-password" in rendered
    assert "service-token" not in rendered
    assert "hidden" in rendered
    assert "secret-value" not in rendered


async def _secret_manager_rows() -> list[list[str]]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SecretManagerPanel)
        deadline = time.monotonic() + 2
        while panel.manager_table.row_count < 2:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for secret managers.")
            await pilot.pause(0.05)
        return [
            [str(cell) for cell in panel.manager_table.get_row_at(index)]
            for index in range(panel.manager_table.row_count)
        ]


def test_secret_manager_table_stays_compact() -> None:
    rows = asyncio.run(_secret_manager_rows())

    assert all(len(row) == 1 for row in rows)
    rendered = "\n".join(" ".join(row) for row in rows)
    assert "vault-bundle" not in rendered
    assert "docker" not in rendered


async def _service_secret_manager_panel_text() -> str:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SecretManagerPanel)
        app.query_one("#main-tabs", TabbedContent).active = SECRET_MANAGER_TAB_ID
        deadline = time.monotonic() + 2
        while panel.manager_table.row_count < 2:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for secret managers.")
            await pilot.pause(0.05)
        panel.manager_table.cursor_coordinate = (1, 0)
        panel.manager_table.action_select_cursor()
        deadline = time.monotonic() + 2
        rows: list[str] = []
        while "service-token" not in "\n".join(rows):
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for service secrets.")
            rows = [
                " ".join(str(cell) for cell in panel.table.get_row_at(index))
                for index in range(panel.table.row_count)
            ]
            await pilot.pause(0.05)
        return "\n".join([_render_text(panel.summary.content), *rows])


def test_secret_manager_tab_lists_service_manager_keys_on_selection() -> None:
    rendered = asyncio.run(_service_secret_manager_panel_text())

    assert "service-token" in rendered
    assert "api-token" not in rendered
    assert "service-secret-value" not in rendered
    assert "vault-bundle" in rendered
    assert "docker" in rendered


async def _add_secret_via_dialog() -> tuple[dict, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SecretManagerPanel)
        app.query_one("#main-tabs", TabbedContent).active = SECRET_MANAGER_TAB_ID
        deadline = time.monotonic() + 2
        while panel.table.row_count == 0:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for secret-manager panel.")
            await pilot.pause(0.05)
        app.query_one("#add-secret", Button).press()
        await pilot.pause()
        app.screen.query_one("#secret-edit-key", Input).value = "new-token"
        app.screen.query_one("#secret-edit-value", TextArea).load_text(
            '{"token": "created"}'
        )
        app.screen.query_one("#confirm-secret-edit", Button).press()
        deadline = time.monotonic() + 2
        while "created" not in _secret_detail_text(panel):
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for saved secret.")
            await pilot.pause(0.05)
        return app.secret_store, _secret_detail_text(panel)


def test_secret_manager_add_secret_dialog_saves_json_value() -> None:
    store, detail = asyncio.run(_add_secret_via_dialog())

    assert store["new-token"] == {"token": "created"}
    assert "new-token" in detail
    assert "created" in detail


async def _edit_secret_inline() -> tuple[dict, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SecretManagerPanel)
        app.query_one("#main-tabs", TabbedContent).active = SECRET_MANAGER_TAB_ID
        deadline = time.monotonic() + 2
        while panel.table.row_count == 0:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for secret-manager panel.")
            await pilot.pause(0.05)
        panel.table.cursor_coordinate = (0, 0)
        app.query_one("#update-secret", Button).press()
        deadline = time.monotonic() + 2
        while not panel.detail_editor.display:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for editable secret.")
            await pilot.pause(0.05)
        panel.detail_editor.load_text('{"token": "updated"}')
        app.query_one("#update-secret", Button).press()
        deadline = time.monotonic() + 2
        while app.secret_store["api-token"] != {"token": "updated"}:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for updated secret.")
            await pilot.pause(0.05)
        return app.secret_store, _secret_detail_text(panel)


def test_secret_manager_edit_secret_inline_updates_value() -> None:
    store, detail = asyncio.run(_edit_secret_inline())

    assert store["api-token"] == {"token": "updated"}
    assert "updated" in detail


async def _activate_service_secret_manager() -> tuple[str, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SecretManagerPanel)
        app.query_one("#main-tabs", TabbedContent).active = SECRET_MANAGER_TAB_ID
        deadline = time.monotonic() + 2
        while panel.manager_table.row_count < 2:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for secret managers.")
            await pilot.pause(0.05)
        panel.manager_table.cursor_coordinate = (1, 0)
        panel.manager_table.action_select_cursor()
        deadline = time.monotonic() + 2
        while not panel.can_activate_selected_manager():
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for activatable manager.")
            await pilot.pause(0.05)
        await pilot.press("ctrl+a")
        deadline = time.monotonic() + 2
        while "External Vault" not in app.query_one("#infra-tree").root.label.plain:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for active manager switch.")
            await pilot.pause(0.05)
        return (
            app.workspace.active_secret_manager_name,
            app.query_one("#infra-tree").root.label.plain,
        )


def test_secret_manager_ctrl_a_activates_selected_manager() -> None:
    active_name, root_label = asyncio.run(_activate_service_secret_manager())

    assert active_name == "External Vault"
    assert root_label == "test-project  Secrets: External Vault"


async def _secret_manager_revealed_text() -> str:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        panel = app.query_one(SecretManagerPanel)
        app.query_one("#main-tabs", TabbedContent).active = SECRET_MANAGER_TAB_ID
        deadline = time.monotonic() + 2
        while panel.table.row_count == 0:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for secret-manager panel.")
            await pilot.pause(0.05)
        panel.table.focus()
        panel.table.cursor_coordinate = (0, 0)
        await pilot.press("enter")
        deadline = time.monotonic() + 2
        while "secret-value" not in _secret_detail_text(panel):
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for revealed secret.")
            await pilot.pause(0.05)
        return _secret_detail_text(panel)


def test_secret_manager_table_enter_reveals_selected_secret() -> None:
    rendered = asyncio.run(_secret_manager_revealed_text())

    assert "api-token" in rendered
    assert "secret-value" in rendered
    assert '"password"' not in rendered


async def _initial_dashboard_overview() -> tuple[str, str, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.query_one(DashboardScreen)
        tabs = screen.query_one("#main-tabs", TabbedContent)
        overview = screen.query_one(OverviewPanel)
        server_tab = tabs.get_tab(SERVER_TEMPLATES_TAB_ID)
        return (
            tabs.active,
            server_tab.styles.display,
            _render_text(overview.content),
        )


def test_dashboard_initially_shows_project_root_overview() -> None:
    active_tab, server_tab_display, overview = asyncio.run(
        _initial_dashboard_overview()
    )

    assert active_tab == "overview-tab"
    assert server_tab_display == "block"
    assert "Infrastructure Overview" in overview
    assert "No infrastructure available." in overview


async def _project_actions_display_for(selection: SelectionInfo) -> bool:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(selection)
        await pilot.pause()
        return app.query_one(ProjectActions).display


def test_project_actions_show_only_for_project_root() -> None:
    assert asyncio.run(_project_actions_display_for(SelectionInfo(type="root"))) is True
    assert asyncio.run(_project_actions_display_for(SelectionInfo(type="bundle"))) is False


async def _add_bundle_project_action_opens_server_templates() -> str:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        app.query_one("#add-bundle-from-server-template", Button).press()
        await pilot.pause(0.1)
        return app.query_one("#main-tabs", TabbedContent).active


def test_project_add_bundle_action_opens_server_templates_tab() -> None:
    assert (
        asyncio.run(_add_bundle_project_action_opens_server_templates())
        == SERVER_TEMPLATES_TAB_ID
    )


async def _project_action_button_row() -> list[str | None]:
    app = DashboardTestApp()
    async with app.run_test():
        row = app.query_one("#project-action-content")
        return [child.id for child in row.children if isinstance(child, Button)]


def test_project_actions_put_add_bundle_and_rename_next_to_each_other() -> None:
    assert asyncio.run(_project_action_button_row()) == [
        "rename-project",
        "add-bundle-from-server-template",
    ]


async def _rename_project_from_action_modal() -> tuple[str, list[str], str, str]:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        await screen.handle_project_rename_requested(ProjectActions.RenameRequested())
        await pilot.pause()

        app.screen.query_one("#rename-project-name", Input).value = "renamed-project"
        await pilot.click("#confirm-project-rename")

        deadline = time.monotonic() + 2
        while app.workspace.name != "renamed-project":
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for project rename.")
            await pilot.pause(0.05)

        overview = screen.query_one(OverviewPanel)
        return (
            app.workspace.name,
            app.commits,
            screen.query_one("#infra-tree", InfraTree).root.label.plain,
            _render_text(overview.content),
        )


def test_project_rename_action_updates_workspace_and_root_label() -> None:
    project_name, commits, root_label, overview = asyncio.run(
        _rename_project_from_action_modal()
    )

    assert project_name == "renamed-project"
    assert commits == ["renamed-project"]
    assert root_label == "renamed-project  Secrets: Embedded Project Storage"
    assert "Infrastructure Overview" in overview


async def _root_label() -> str:
    app = DashboardTestApp()
    async with app.run_test():
        return app.query_one("#infra-tree").root.label.plain


def test_root_highlights_active_secret_manager() -> None:
    assert asyncio.run(_root_label()) == (
        "test-project  Secrets: Embedded Project Storage"
    )


async def _bundle_label() -> str:
    app = DashboardTestApp()
    server = SimpleNamespace(ip="10.0.0.5", backend=["docker", "k3s-agent"])
    bundle = SimpleNamespace(name="dev", server=server, services=[])
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    async with app.run_test():
        tree = app.query_one(InfraTree)
        return tree.root.children[0].label.plain


def test_bundle_tree_label_shows_backend_type() -> None:
    assert asyncio.run(_bundle_label()) == (
        "Bundle: dev  Backend: docker, k3s_agent"
    )


async def _service_actions_display_for(selection: SelectionInfo) -> bool:
    app = DashboardTestApp()
    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(selection)
        await pilot.pause()
        return app.query_one(ServiceActions).display


def test_service_actions_show_only_for_service_nodes() -> None:
    assert (
        asyncio.run(
            _service_actions_display_for(
                SelectionInfo(type="service", service=SimpleNamespace(name="svc"))
            )
        )
        is True
    )
    assert (
        asyncio.run(_service_actions_display_for(SelectionInfo(type="bundle")))
        is False
    )


async def _rename_service_from_action_modal() -> tuple[str, str]:
    app = DashboardTestApp()
    service = SimpleNamespace(name="mlflow", state="running")
    bundle = SimpleNamespace(
        name="dev",
        server=SimpleNamespace(ip="10.0.0.5", state="running", backend=["docker"]),
        services=[service],
    )
    infra = SimpleNamespace(bundles=[bundle])
    infra.get_service = lambda name: service if service.name == name else None
    infra.list_service_names = lambda: [service.name]
    infra.get_bundle_by_service = lambda value: bundle if value is service else None
    app.workspace.infrastructure = infra

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        selection = SelectionInfo(type="service", bundle=bundle, service=service)
        screen._apply_selection(selection)
        await screen.handle_service_rename_requested(ServiceActions.RenameRequested())
        await pilot.pause()

        app.screen.query_one("#rename-service-name", Input).value = "tracking"
        await pilot.click("#confirm-service-rename")

        deadline = time.monotonic() + 2
        while service.name != "tracking":
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for service rename.")
            await pilot.pause(0.05)

        return service.name, screen.query_one("#infra-tree", InfraTree).root.children[
            0
        ].children[1].label.plain


def test_service_rename_action_updates_service_and_tree_label() -> None:
    service_name, tree_label = asyncio.run(_rename_service_from_action_modal())

    assert service_name == "tracking"
    assert tree_label == "Service: tracking"


async def _edit_bundle_tags_from_action_modal() -> tuple[list[str], list[str], str]:
    app = DashboardTestApp()
    server = SimpleNamespace(ip="10.0.0.5", state="running", backend=["docker"])
    bundle = SimpleNamespace(
        name="dev",
        server=server,
        services=[],
        tags=["prod"],
    )
    other_bundle = SimpleNamespace(
        name="shared",
        server=SimpleNamespace(ip="10.0.0.6", backend=["docker"]),
        services=[],
        tags=["shared"],
    )
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle, other_bundle])

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        selection = SelectionInfo(type="bundle", bundle=bundle, server=server)
        screen._apply_selection(selection)
        await screen.handle_bundle_tags_requested(ServerActions.EditTagsRequested())
        await pilot.pause()

        app.screen.query_one("#bundle-tag-selection", SelectionList).select("shared")
        app.screen.query_one("#new-bundle-tags", Input).value = "gpu, prod"
        await pilot.click("#confirm-bundle-tags")

        deadline = time.monotonic() + 2
        while bundle.tags != ["prod", "shared", "gpu"]:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for bundle tags update.")
            await pilot.pause(0.05)

        overview = screen.query_one(OverviewPanel)
        return bundle.tags, app.commits, _render_text(overview.content)


def test_bundle_edit_tags_action_updates_tags_and_overview() -> None:
    tags, commits, overview = asyncio.run(_edit_bundle_tags_from_action_modal())

    assert tags == ["prod", "shared", "gpu"]
    assert commits == ["test-project"]
    assert "prod" in overview
    assert "shared" in overview
    assert "gpu" in overview


async def _add_server_from_template_modal() -> tuple[list[tuple[object, dict]], str, str]:
    app = DashboardTestApp()
    calls = []
    bundle = SimpleNamespace(
        name="127.0.0.1",
        server=SimpleNamespace(ip="127.0.0.1", backend=["connector"]),
        services=[],
    )

    def add_server_from_config(config, params):
        calls.append((config, params))
        app.workspace.infrastructure.bundles.append(bundle)
        return OperationResult(True, 0, "Added server 127.0.0.1.", {"bundle": bundle})

    app.workspace.add_server_from_config = add_server_from_config
    spec = TemplateFormSpec(
        title="Add Test Server",
        fields=[TemplateFieldSpec("host", "Host")],
        materialize=lambda values, infra: {"${MLOX_IP}": values["host"]},
    )
    config = SimpleNamespace(
        id="test-server",
        name="Test Server",
        get_ui_handler=lambda ui, handler: lambda infra, cfg: spec,
    )

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        await screen.handle_server_template_configure_requested(
            TemplatePanel.ConfigureTemplateRequested(config)
        )
        await pilot.pause()
        app.screen.query_one("#template-field-host", Input).value = "127.0.0.1"
        await pilot.click("#confirm-template-setup")

        deadline = time.monotonic() + 2
        while not calls or tree_label(app.query_one(InfraTree)) != (
            "Bundle: 127.0.0.1  Backend: connector"
        ):
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for server add.")
            await pilot.pause(0.05)

        tree = screen.query_one(InfraTree)
        return calls, tree.root.children[0].label.plain, tree.cursor_node.label.plain


def test_server_template_modal_adds_server_and_refreshes_tree() -> None:
    calls, bundle_label, selected_label = asyncio.run(_add_server_from_template_modal())

    assert calls[0][1] == {"${MLOX_IP}": "127.0.0.1"}
    assert bundle_label == "Bundle: 127.0.0.1  Backend: connector"
    assert selected_label == bundle_label


async def _setup_uninitialized_bundle_from_action() -> tuple[str, str, list[str]]:
    app = DashboardTestApp()
    calls: list[str] = []
    server = SimpleNamespace(
        ip="10.0.0.5",
        backend=["kubernetes"],
        state="un-initialized",
    )
    bundle = SimpleNamespace(name="dev", server=server, services=[])
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    def setup_server(ip: str):
        calls.append(ip)
        server.state = "running"
        return OperationResult(True, 0, "Server 10.0.0.5 set up.", {})

    app.workspace.setup_server = setup_server

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        app.query_one("#setup-bundle", Button).press()

        deadline = time.monotonic() + 2
        while server.state != "running":
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for bundle setup.")
            await pilot.pause(0.05)

        tree = screen.query_one(InfraTree)
        return server.state, tree.root.children[0].label.plain, calls


def test_setup_bundle_action_initializes_bundle_and_refreshes_tree() -> None:
    state, label, calls = asyncio.run(_setup_uninitialized_bundle_from_action())

    assert state == "running"
    assert label == "Bundle: dev  Backend: kubernetes"
    assert calls == ["10.0.0.5"]


async def _remove_bundle_from_action() -> tuple[int, list[str]]:
    app = DashboardTestApp()
    calls: list[str] = []
    server = SimpleNamespace(ip="10.0.0.5", backend=["kubernetes"], state="running")
    bundle = SimpleNamespace(name="dev", server=server, services=[])
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    def teardown_server(ip: str):
        calls.append(ip)
        app.workspace.infrastructure.bundles.remove(bundle)
        return OperationResult(True, 0, "Server 10.0.0.5 removed.", {})

    app.workspace.teardown_server = teardown_server

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        app.query_one("#remove-bundle", Button).press()
        await pilot.pause()
        app.screen.query_one("#confirm-remove-bundle", Button).press()

        deadline = time.monotonic() + 2
        while app.workspace.infrastructure.bundles:
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for bundle removal.")
            await pilot.pause(0.05)

        return len(screen.query_one(InfraTree).root.children), calls


def test_remove_bundle_action_confirms_and_removes_bundle() -> None:
    root_child_count, calls = asyncio.run(_remove_bundle_from_action())

    assert root_child_count == 1
    assert calls == ["10.0.0.5"]


def tree_label(tree: InfraTree) -> str:
    return tree.cursor_node.label.plain


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


async def _expanded_tree_flags_after_mount() -> tuple[bool, list[bool]]:
    app = DashboardTestApp()
    server = SimpleNamespace(ip="10.0.0.5")
    services = [SimpleNamespace(name="MLflow"), SimpleNamespace(name="Postgres")]
    bundle = SimpleNamespace(name="dev", server=server, services=services)
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    async with app.run_test():
        tree = app.query_one(InfraTree)
        return tree.root.is_expanded, [
            child.is_expanded for child in tree.root.children if child.allow_expand
        ]


def test_project_tree_is_fully_expanded_after_mount() -> None:
    root_expanded, child_expanded = asyncio.run(_expanded_tree_flags_after_mount())

    assert root_expanded is True
    assert child_expanded == [True]


async def _uninitialized_bundle_tree_entry() -> tuple[bool, str]:
    app = DashboardTestApp()
    server = SimpleNamespace(
        ip="10.0.0.5",
        backend=["kubernetes"],
        state="un-initialized",
    )
    bundle = SimpleNamespace(name="dev", server=server, services=[])
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    async with app.run_test():
        tree = app.query_one(InfraTree)
        node = tree.root.children[0]
        return node.allow_expand, node.label.plain


def test_uninitialized_bundle_tree_entry_is_leaf() -> None:
    allow_expand, label = asyncio.run(_uninitialized_bundle_tree_entry())

    assert allow_expand is False
    assert label == "Bundle: dev  Backend: kubernetes  State: pending"


async def _empty_bundle_tree_children() -> list[str]:
    app = DashboardTestApp()
    server = SimpleNamespace(
        ip="10.0.0.5",
        backend=["docker"],
        state="running",
    )
    bundle = SimpleNamespace(name="dev", server=server, services=[])
    app.workspace.infrastructure = SimpleNamespace(bundles=[bundle])

    async with app.run_test():
        tree = app.query_one(InfraTree)
        bundle_node = tree.root.children[0]
        return [child.label.plain for child in bundle_node.children]


def test_empty_bundle_tree_has_no_no_services_leaf() -> None:
    children = asyncio.run(_empty_bundle_tree_children())

    assert children == ["Server: 10.0.0.5"]


def test_bundle_selection_shows_only_service_templates_tab() -> None:
    (
        server_display,
        secret_display,
        firewall_display,
        monitor_display,
        models_display,
        service_display,
        logs_display,
    ) = asyncio.run(_visible_tabs_for(SelectionInfo(type="bundle")))

    assert server_display == "none"
    assert secret_display == "none"
    assert firewall_display == "none"
    assert monitor_display == "none"
    assert models_display == "none"
    assert service_display == "block"
    assert logs_display == "none"


async def _service_tab_display_for_uninitialized_bundle() -> str:
    app = DashboardTestApp()
    server = SimpleNamespace(ip="10.0.0.5", state="un-initialized")
    bundle = SimpleNamespace(name="dev", server=server, services=[])

    async with app.run_test() as pilot:
        screen = app.query_one(DashboardScreen)
        screen._apply_selection(
            SelectionInfo(type="bundle", bundle=bundle, server=server)
        )
        await pilot.pause()
        tabs = screen.query_one("#main-tabs", TabbedContent)
        return tabs.get_tab(SERVICE_TEMPLATES_TAB_ID).styles.display


def test_uninitialized_bundle_selection_hides_service_templates_tab() -> None:
    assert asyncio.run(_service_tab_display_for_uninitialized_bundle()) == "none"


def test_server_selection_hides_template_tabs() -> None:
    (
        server_display,
        secret_display,
        firewall_display,
        monitor_display,
        models_display,
        service_display,
        logs_display,
    ) = asyncio.run(_visible_tabs_for(SelectionInfo(type="server")))

    assert server_display == "none"
    assert secret_display == "none"
    assert firewall_display == "none"
    assert monitor_display == "none"
    assert models_display == "none"
    assert service_display == "none"
    assert logs_display == "block"


def test_service_selection_shows_history_and_logs_tab() -> None:
    (
        server_display,
        secret_display,
        firewall_display,
        monitor_display,
        models_display,
        service_display,
        logs_display,
    ) = asyncio.run(_visible_tabs_for(SelectionInfo(type="service")))

    assert server_display == "none"
    assert secret_display == "none"
    assert firewall_display == "none"
    assert monitor_display == "none"
    assert models_display == "none"
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


async def _reload_loading_state(monkeypatch) -> tuple[bool, bool]:
    app = DashboardTestApp()
    release = threading.Event()

    def reload_workspace(workspace):
        release.wait(timeout=2)
        workspace.name = "test-project-reloaded"
        workspace.infrastructure = SimpleNamespace(bundles=[])
        return OperationResult(True, 0, "reloaded")

    monkeypatch.setattr(
        "mlox.tui.screens.dashboard.screen.reload_project_workspace",
        reload_workspace,
    )

    async with app.run_test() as pilot:
        await pilot.press("R")
        await pilot.pause()
        screen = app.query_one(DashboardScreen)
        loading = screen.query_one("#project-reload-loading")
        loading_visible = loading.display
        release.set()
        for _ in range(20):
            await pilot.pause(0.05)
            if not loading.display:
                break
        return loading_visible, loading.display


def test_reload_binding_shows_loading_indicator(monkeypatch) -> None:
    loading_visible, loading_after_reload = asyncio.run(
        _reload_loading_state(monkeypatch)
    )

    assert loading_visible is True
    assert loading_after_reload is False
