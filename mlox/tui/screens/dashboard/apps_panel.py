"""Project-wide application overview."""
from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.apps import describe_apps
from mlox.application.use_cases.services import open_service_web_ui
from .model import SelectionInfo


class AppsPanel(Static):
    """List installed apps and open their browser interfaces."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs):
        super().__init__(*children, **kwargs)
        self._apps: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="apps-content"):
            with Horizontal(id="apps-metrics"):
                yield Static(id="apps-metric-total", classes="app-metric")
                yield Static(id="apps-metric-running", classes="app-metric")
                yield Static(id="apps-metric-stopped", classes="app-metric")
                yield Static(id="apps-metric-urls", classes="app-metric")
            with Horizontal(id="apps-actions"):
                yield Static("Project Apps", id="apps-title")
                yield Button("Open App", id="open-app")
                yield Button("Refresh Apps", id="refresh-apps")
            yield Static("Status reflects the last recorded service state.", id="apps-status")
            table = DataTable(id="apps-table")
            table.cursor_type = "row"
            table.add_columns("App", "Bundle", "Server", "State", "URL")
            yield table

    def on_mount(self) -> None:
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        self.display = bool(selection and selection.type == "root")
        if self.display:
            self.load()

    def load(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self.query_one("#refresh-apps", Button).disabled = True
        self.query_one("#apps-status", Static).update("Loading apps...")

        def load_apps() -> None:
            result = describe_apps(infra)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(load_apps, thread=True, exclusive=True, group="project-apps")

    def _show_result(self, result) -> None:
        if not self.is_attached or not self.selection or self.selection.type != "root":
            return
        self.query_one("#refresh-apps", Button).disabled = False
        self._apps = list((result.data or {}).get("apps", [])) if result.success else []
        table = self.query_one("#apps-table", DataTable)
        table.clear(columns=False)
        for row in self._apps:
            table.add_row(row["name"], row["bundle"], row["server"], row["state"], row["url"] or "—")
        metrics = (result.data or {}).get("metrics", {})
        for name, label in (("total", "Apps"), ("running", "Running"), ("stopped", "Stopped"), ("urls", "Web UIs")):
            value = metrics.get("with_url" if name == "urls" else name, 0)
            self.query_one(f"#apps-metric-{name}", Static).update(Text.from_markup(f"[bold]{value}[/bold]\n{label}"))
        self.query_one("#apps-status", Static).update(
            "Status reflects the last recorded service state." if self._apps else result.message
        )
        self.query_one("#open-app", Button).disabled = not bool(self._apps)

    @on(Button.Pressed, "#refresh-apps")
    def refresh_apps(self, _: Button.Pressed) -> None:
        self.load()

    @on(Button.Pressed, "#open-app")
    def open_app(self, _: Button.Pressed) -> None:
        index = self.query_one("#apps-table", DataTable).cursor_row
        if index is None or not 0 <= index < len(self._apps):
            self.notify("Select an app first.", severity="warning")
            return
        result = open_service_web_ui(self._apps[index]["service_ref"])
        self.notify(result.message, severity="information" if result.success else "warning")
