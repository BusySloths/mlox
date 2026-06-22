"""Main dashboard screen composition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header, Static, TabPane, TabbedContent, Tabs

from .app_log_panel import AppLogPanel
from .history_panel import HistoryPanel
from .log_panel import LogPanel
from .model import SelectionChanged, SelectionInfo
from .overview_panel import OverviewPanel
from .server_actions import ServerActions
from .server_info_panel import ServerInfoPanel
from .stats_panel import StatsPanel
from .template_panel import TemplatePanel
from .tree import InfraTree
from mlox.application.use_cases.project import reload_project_workspace
from mlox.application.use_cases.services import build_service_ui_widget


TELEMETRY_TAB_ID = "service-tui-tab"
SERVER_TEMPLATES_TAB_ID = "server-templates-tab"
SERVICE_TEMPLATES_TAB_ID = "service-templates-tab"
OVERVIEW_TAB_ID = "overview-tab"
LOGS_TAB_ID = "logs-tab"
SERVER_INFO_TAB_ID = "server-info-tab"
SIDEBAR_DEFAULT_WIDTH = 32
SIDEBAR_MIN_WIDTH = 24
SIDEBAR_MAX_WIDTH = 72
SIDEBAR_STEP = 4


class DashboardScreen(Screen):
    """Main dashboard shown after a successful login."""

    BINDINGS = [
        ("l", "toggle_app_logs", "Logs"),
        ("O", "open_terminal", "Open Terminal"),
        ("R", "reload_infrastructure", "Reload"),
        ("[", "narrow_sidebar", "Narrow Sidebar"),
        ("]", "widen_sidebar", "Widen Sidebar"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._sidebar_width = SIDEBAR_DEFAULT_WIDTH

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, classes="app-header")
        with Container(id="main-area"):
            with Container(id="sidebar"):
                yield InfraTree()
            with Container(id="detail-panel"):
                with Container(id="upper-pane"):
                    with Horizontal(id="summary-pane"):
                        with TabbedContent(id="main-tabs"):
                            with TabPane("Overview", id=OVERVIEW_TAB_ID):
                                with VerticalScroll(id="overview-scroll"):
                                    yield OverviewPanel(id="selection-overview")
                                    yield StatsPanel(id="selection-stats")
                                    yield ServerActions(id="selection-server-actions")
                            with TabPane("History & Logs", id=LOGS_TAB_ID):
                                yield LogPanel(id="selection-logs")
                                yield HistoryPanel(id="selection-history")
                            with TabPane("Server Info", id=SERVER_INFO_TAB_ID):
                                yield ServerInfoPanel(id="selection-server-info")
                            with TabPane("Server Templates", id=SERVER_TEMPLATES_TAB_ID):
                                yield TemplatePanel(
                                    id="server-template-panel", template_type="server"
                                )
                            with TabPane("Service Templates", id=SERVICE_TEMPLATES_TAB_ID):
                                yield TemplatePanel(
                                    id="service-template-panel", template_type="service"
                                )
                            with TabPane("Telemetry", id=TELEMETRY_TAB_ID):
                                yield Container(id="service-tui-container")
        yield AppLogPanel(id="app-log-drawer")
        yield Footer(classes="app-footer")

    def on_mount(self) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        self._set_telemetry_tab_visible(False)
        self._update_template_tabs(tree.root.data)
        container = self.query_one("#service-tui-container", Container)
        self._mount_placeholder(
            container, "Select a service to inspect telemetry metrics."
        )
        self._set_app_log_drawer_visible(False)
        self._apply_sidebar_width()

    def on_selection_changed(self, message: SelectionChanged) -> None:
        self._apply_selection(message.selection)

    def _apply_selection(self, selection: SelectionInfo | None) -> None:
        overview = self.query_one(OverviewPanel)
        overview.selection = selection
        server_actions = self.query_one(ServerActions)
        server_actions.selection = selection
        server_info = self.query_one(ServerInfoPanel)
        server_info.selection = selection
        stats = self.query_one(StatsPanel)
        stats.selection = selection
        logs = self.query_one(LogPanel)
        logs.selection = selection
        history = self.query_one(HistoryPanel)
        history.selection = selection
        for templates in self.query(TemplatePanel):
            templates.selection = selection
        self._update_template_tabs(selection)
        self._update_tui_panel(selection)

    def action_reload_infrastructure(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        if not workspace:
            self.notify(
                "Cannot reload infrastructure because the project workspace is incomplete.",
                severity="error",
            )
            return
        project = str(workspace.path)

        self.notify(f"Reloading project infrastructure for {project}...")

        def reload_workspace() -> None:
            result = reload_project_workspace(workspace)
            if not result.success:
                self.app.call_from_thread(
                    self._show_reload_error,
                    result.message,
                )
                return
            self.app.call_from_thread(
                self._apply_reloaded_workspace,
                project,
            )

        self.app.run_worker(
            reload_workspace,
            thread=True,
            exclusive=True,
            group="project-reload",
        )

    def _show_reload_error(self, message: str) -> None:
        self.notify(message, severity="error")

    def _apply_reloaded_workspace(self, project: str) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        self._apply_selection(tree.root.data)
        self.notify(f"Reloaded project infrastructure for {project}.")

    def _update_template_tabs(self, selection: SelectionInfo | None) -> None:
        self._set_tab_visible(
            SERVER_TEMPLATES_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            SERVICE_TEMPLATES_TAB_ID,
            selection.type == "bundle" if selection else False,
        )
        self._set_tab_visible(
            LOGS_TAB_ID,
            selection.type in {"server", "service"} if selection else False,
        )
        self._set_tab_visible(
            SERVER_INFO_TAB_ID,
            selection.type in {"bundle", "server"} if selection else False,
        )

    def _update_tui_panel(self, selection: SelectionInfo | None) -> None:
        container = self.query_one("#service-tui-container", Container)
        for child in list(container.children):
            child.remove()

        self._set_telemetry_tab_visible(False)

        if not selection or selection.type != "service" or not selection.service:
            self._mount_placeholder(
                container, "Select a service to inspect telemetry metrics."
            )
            return

        workspace = getattr(self.app, "workspace", None)
        infra = workspace.infrastructure if workspace else None
        if not infra or not selection.bundle:
            self._mount_placeholder(
                container,
                "Telemetry is unavailable because the infrastructure is not loaded.",
            )
            return

        result = build_service_ui_widget(infra, selection.bundle, selection.service)
        if not result.success:
            self._mount_placeholder(container, result.message)
            return

        widget = result.data["widget"] if result.data else None
        if not isinstance(widget, Widget):
            self._mount_placeholder(
                container,
                "Telemetry provider returned an unexpected payload.",
            )
            return

        container.mount(widget)
        self._set_telemetry_tab_visible(True)

    def _set_telemetry_tab_visible(self, visible: bool) -> None:
        self._set_tab_visible(TELEMETRY_TAB_ID, visible)

    def _set_tab_visible(self, tab_id: str, visible: bool) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        try:
            if visible:
                tabs.show_tab(tab_id)
            else:
                if tabs.active == tab_id:
                    tabs.active = OVERVIEW_TAB_ID
                tabs.hide_tab(tab_id)
        except Tabs.TabError:
            pass

    def action_toggle_app_logs(self) -> None:
        drawer = self.query_one("#app-log-drawer", AppLogPanel)
        self._set_app_log_drawer_visible(drawer.styles.display == "none")

    def action_open_terminal(self) -> None:
        server_actions = self.query_one(ServerActions)
        if not server_actions.display:
            self.notify(
                "Select a bundle or server to open an SSH terminal.",
                severity="warning",
            )
            return
        server_actions.open_terminal()

    def _set_app_log_drawer_visible(self, visible: bool) -> None:
        drawer = self.query_one("#app-log-drawer", AppLogPanel)
        drawer.styles.display = "block" if visible else "none"

    def action_narrow_sidebar(self) -> None:
        self._resize_sidebar(-SIDEBAR_STEP)

    def action_widen_sidebar(self) -> None:
        self._resize_sidebar(SIDEBAR_STEP)

    def _resize_sidebar(self, delta: int) -> None:
        self._sidebar_width = max(
            SIDEBAR_MIN_WIDTH,
            min(SIDEBAR_MAX_WIDTH, self._sidebar_width + delta),
        )
        self._apply_sidebar_width()

    def _apply_sidebar_width(self) -> None:
        sidebar = self.query_one("#sidebar", Container)
        sidebar.styles.width = self._sidebar_width

    def _mount_placeholder(self, container: Container, message: str) -> None:
        container.mount(Static(message, classes="service-tui-placeholder"))
