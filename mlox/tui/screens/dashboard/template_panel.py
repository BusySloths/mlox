"""Template panel for browsing server and service configs."""

from __future__ import annotations

from typing import Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static

from mlox.config import load_all_server_configs, load_all_service_configs

from .model import SelectionInfo


class TemplatePanel(Container):
    """Context-aware template browser."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="template-scroll-wrapper"):
            yield Static(id="template-content")

    @property
    def content(self) -> Static:
        return self.query_one("#template-content", Static)

    def on_mount(self) -> None:
        self._show_default()

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if selection and selection.type in {"server", "bundle"}:
            self._show_server_templates()
        elif selection and selection.type == "service":
            self._show_service_templates()
        else:
            self._show_default()

    def _show_default(self) -> None:
        message = Text.from_markup(
            "[b]Templates[/b]\n\nSelect a server to browse matching server configs or a service to browse service configs."
        )
        self.content.update(Panel(message, title="Templates", border_style="green"))

    def _build_template_table(self, configs, title: str) -> Panel:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Name", style="cyan")
        table.add_column("Version", justify="left")
        table.add_column("Maintainer", justify="left")
        table.add_column("Path", justify="left")
        if configs:
            for cfg in configs:
                table.add_row(
                    getattr(cfg, "name", "-"),
                    str(getattr(cfg, "version", "-")),
                    getattr(cfg, "maintainer", "-"),
                    getattr(cfg, "path", "-"),
                )
        else:
            table.add_row("-", "-", "-", "-")
        return Panel(table, title=title, border_style="green")

    def _show_server_templates(self) -> None:
        configs = load_all_server_configs()
        panel = self._build_template_table(configs, "Server Templates")
        self.content.update(panel)

    def _show_service_templates(self) -> None:
        configs = load_all_service_configs()
        panel = self._build_template_table(configs, "Service Templates")
        self.content.update(panel)
