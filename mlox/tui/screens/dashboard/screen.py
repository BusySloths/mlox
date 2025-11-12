"""Main dashboard screen composition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header, Static, TabPane, TabbedContent

from .history_panel import HistoryPanel
from .log_panel import LogPanel
from .model import SelectionChanged, SelectionInfo
from .overview_panel import OverviewPanel
from .stats_panel import StatsPanel
from .template_panel import TemplatePanel
from .tree import InfraTree


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
                            with TabPane("Telemetry", id="service-tui-tab"):
                                yield Container(id="service-tui-container")
        yield Footer(classes="app-footer")

    def on_mount(self) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()
        tui_tab = self.query_one("#service-tui-tab", TabPane)
        tui_tab.display = False
        container = self.query_one("#service-tui-container", Container)
        container.mount(Static("Select a service to inspect telemetry metrics.", id="service-tui-placeholder"))

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

        tui_tab = self.query_one("#service-tui-tab", TabPane)
        tui_tab.display = False

        if not selection or selection.type != "service" or not selection.service:
            container.mount(Static("Select a service to inspect telemetry metrics.", id="service-tui-placeholder"))
            return

        session = getattr(self.app, "session", None)
        infra = getattr(session, "infra", None) if session else None
        if not infra or not selection.bundle:
            container.mount(Static("Telemetry is unavailable because the infrastructure is not loaded.", id="service-tui-placeholder"))
            return

        config = infra.get_service_config(selection.service)
        if not config:
            container.mount(Static("Unable to resolve a configuration for the selected service.", id="service-tui-placeholder"))
            return

        callable_settings = config.instantiate_ui("tui_settings")
        if not callable_settings:
            container.mount(Static("Selected service does not provide a telemetry view.", id="service-tui-placeholder"))
            return

        try:
            widget = callable_settings(infra, selection.bundle, selection.service)
        except Exception as exc:  # pragma: no cover - defensive for IO errors
            container.mount(Static(f"Failed to load telemetry: {exc}", id="service-tui-placeholder"))
            return

        if not isinstance(widget, Widget):
            container.mount(Static("Telemetry provider returned an unexpected payload.", id="service-tui-placeholder"))
            return

        container.mount(widget)
        tui_tab.display = True
