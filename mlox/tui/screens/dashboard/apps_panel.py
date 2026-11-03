"""Project-wide application overview."""
from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.apps import UNPROXIED_APPS, describe_apps, open_app
from .model import SelectionInfo


class AppsPanel(Static):
    """List installed apps and open their browser interfaces."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs):
        super().__init__(*children, **kwargs)
        self._apps: list[dict[str, Any]] = []
        self._proxies: list[dict[str, Any]] = []
        self._apps_by_proxy: dict[str, list[dict[str, Any]]] = {}
        self._selected_proxy = UNPROXIED_APPS

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
            with Horizontal(id="apps-browser"):
                proxies = DataTable(id="apps-proxy-table")
                proxies.cursor_type = "row"
                proxies.add_columns("Proxy", "Bundle", "Apps")
                yield proxies
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
        payload = result.data or {}
        self._proxies = list(payload.get("proxies", [])) if result.success else [
            {"id": UNPROXIED_APPS, "name": "No proxy", "bundle": "—", "app_count": 0}
        ]
        self._apps_by_proxy = dict(payload.get("apps_by_proxy", {})) if result.success else {}
        if self._selected_proxy not in {row["id"] for row in self._proxies}:
            self._selected_proxy = UNPROXIED_APPS
        proxies = self.query_one("#apps-proxy-table", DataTable)
        proxies.clear(columns=False)
        selected_index = 0
        for index, row in enumerate(self._proxies):
            proxies.add_row(row["name"], row["bundle"], str(row["app_count"]), key=row["id"])
            if row["id"] == self._selected_proxy:
                selected_index = index
        if self._proxies:
            proxies.cursor_coordinate = (selected_index, 0)
        self._populate_apps()
        metrics = (result.data or {}).get("metrics", {})
        for name, label in (("total", "Apps"), ("running", "Running"), ("stopped", "Stopped"), ("urls", "Web UIs")):
            value = metrics.get("with_url" if name == "urls" else name, 0)
            self.query_one(f"#apps-metric-{name}", Static).update(Text.from_markup(f"[bold]{value}[/bold]\n{label}"))
        self.query_one("#apps-status", Static).update(
            "Select a proxy to see its apps. State is the last recorded service state." if result.success else result.message
        )

    @on(DataTable.RowHighlighted, "#apps-proxy-table")
    def select_proxy(self, event: DataTable.RowHighlighted) -> None:
        key = str(event.row_key.value)
        if key in self._apps_by_proxy:
            self._selected_proxy = key
            self._populate_apps()

    def _populate_apps(self) -> None:
        self._apps = list(self._apps_by_proxy.get(self._selected_proxy, []))
        table = self.query_one("#apps-table", DataTable)
        table.clear(columns=False)
        for row in self._apps:
            urls = row.get("proxy_urls") or []
            table.add_row(row["name"], row["bundle"], row["server"], row["state"], ', '.join(urls) or row["url"] or "—")
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
        result = open_app(self._apps[index])
        self.notify(result.message, severity="information" if result.success else "warning")
