"""Main dashboard screen composition."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, TabPane, TabbedContent

from .history_panel import HistoryPanel
from .log_panel import LogPanel
from .model import SelectionChanged
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
        yield Footer(classes="app-footer")

    def on_mount(self) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()

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
