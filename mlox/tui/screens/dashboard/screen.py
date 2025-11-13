"""Main dashboard screen composition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header, Static, TabPane, TabbedContent, Tabs

from .history_panel import HistoryPanel
from .log_panel import LogPanel
from .model import SelectionChanged, SelectionInfo
from .overview_panel import OverviewPanel
from .stats_panel import StatsPanel
from .template_panel import TemplatePanel
from .tree import InfraTree
from mlox.services.otel.docker import OtelDockerService


TELEMETRY_TAB_ID = "service-tui-tab"


class DashboardScreen(Screen):
    """Main dashboard shown after a successful login."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, classes="app-header")
        with Container(id="main-area"):
            with Container(id="sidebar"):
                yield InfraTree()
            with Container(id="detail-panel"):
                with Container(id="upper-pane"):
                    with Horizontal(id="summary-pane"):
                        with TabbedContent(id="main-tabs"):
                            with TabPane("Overview", id="overview-tab"):
                                with VerticalScroll(id="overview-scroll"):
                                    yield OverviewPanel(id="selection-overview")
                                    yield StatsPanel(id="selection-stats")
                            with TabPane("History & Logs", id="logs-tab"):
                                yield LogPanel(id="selection-logs")
                                yield HistoryPanel(id="selection-history")
                            with TabPane("Templates", id="template-tab"):
                                yield TemplatePanel(id="template-panel")
                            with TabPane("Telemetry", id=TELEMETRY_TAB_ID):
                                yield Container(id="service-tui-container")
        yield Footer(classes="app-footer")

    def on_mount(self) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        self._set_telemetry_tab_visible(False)
        container = self.query_one("#service-tui-container", Container)
        self._mount_placeholder(
            container, "Select a service to inspect telemetry metrics."
        )

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
        templates = self.query_one(TemplatePanel)
        templates.selection = selection
        self._update_tui_panel(selection)

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

        callable_settings = config.instantiate_ui("tui_settings")
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
        tabs = self.query_one("#main-tabs", TabbedContent)
        try:
            if visible:
                tabs.show_tab(TELEMETRY_TAB_ID)
            else:
                tabs.hide_tab(TELEMETRY_TAB_ID)
        except Tabs.TabError:
            pass

    def _mount_placeholder(self, container: Container, message: str) -> None:
        container.mount(Static(message, classes="service-tui-placeholder"))
