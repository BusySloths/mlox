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
from .stats_panel import StatsPanel
from .template_panel import TemplatePanel
from .tree import InfraTree
from mlox.services.otel.docker import OtelDockerService


TELEMETRY_TAB_ID = "service-tui-tab"
SERVER_TEMPLATES_TAB_ID = "server-templates-tab"
SERVICE_TEMPLATES_TAB_ID = "service-templates-tab"
OVERVIEW_TAB_ID = "overview-tab"
SIDEBAR_DEFAULT_WIDTH = 32
SIDEBAR_MIN_WIDTH = 24
SIDEBAR_MAX_WIDTH = 72
SIDEBAR_STEP = 4


class DashboardScreen(Screen):
    """Main dashboard shown after a successful login."""

    BINDINGS = [
        ("l", "toggle_app_logs", "Logs"),
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
                            with TabPane("History & Logs", id="logs-tab"):
                                yield LogPanel(id="selection-logs")
                                yield HistoryPanel(id="selection-history")
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
        selection = message.selection
        overview = self.query_one(OverviewPanel)
        overview.selection = selection
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

    def _update_template_tabs(self, selection: SelectionInfo | None) -> None:
        self._set_tab_visible(
            SERVER_TEMPLATES_TAB_ID,
            selection.type == "root" if selection else False,
        )
        self._set_tab_visible(
            SERVICE_TEMPLATES_TAB_ID,
            selection.type == "bundle" if selection else False,
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

        if not self._is_otel_service(selection.service):
            self._mount_placeholder(
                container,
                "Telemetry is only available for the OpenTelemetry collector service.",
            )
            return

        session = getattr(self.app, "session", None)
        infra = getattr(session, "infra", None) if session else None
        if not infra or not selection.bundle:
            self._mount_placeholder(
                container,
                "Telemetry is unavailable because the infrastructure is not loaded.",
            )
            return

        config = infra.get_service_config(selection.service)
        if not config:
            self._mount_placeholder(
                container,
                "Unable to resolve a configuration for the selected service.",
            )
            return

        callable_settings = config.get_ui_handler("tui", "settings")
        if not callable_settings:
            self._mount_placeholder(
                container,
                "Selected service does not provide a telemetry view.",
            )
            return

        try:
            widget = callable_settings(infra, selection.bundle, selection.service)
        except Exception as exc:  # pragma: no cover - defensive for IO errors
            self._mount_placeholder(
                container,
                f"Failed to load telemetry: {exc}",
            )
            return

        if not isinstance(widget, Widget):
            self._mount_placeholder(
                container,
                "Telemetry provider returned an unexpected payload.",
            )
            return

        container.mount(widget)
        self._set_telemetry_tab_visible(True)

    def _is_otel_service(self, service: object | None) -> bool:
        return isinstance(service, OtelDockerService)

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
