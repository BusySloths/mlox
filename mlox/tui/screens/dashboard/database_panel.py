"""Project database overview panel."""

from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.databases import describe_databases
from mlox.application.use_cases.services import build_service_ui_widget

from .model import SelectionInfo


class DatabasePanel(Static):
    """Root-level overview of database-capable services."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._rows: list[dict[str, Any]] = []
        self._row_keys: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="database-content"):
            with Horizontal(id="database-metrics"):
                yield Static(id="database-metric-total", classes="database-metric")
                yield Static(id="database-metric-running", classes="database-metric")
                yield Static(id="database-metric-engines", classes="database-metric")
                yield Static(id="database-metric-endpoints", classes="database-metric")
            with Horizontal(id="database-actions"):
                yield Static("Project Databases", id="database-title")
                yield Button("Refresh", id="refresh-databases")
            table = DataTable(id="database-table")
            table.cursor_type = "row"
            table.add_columns(
                "Name",
                "Engine",
                "State",
                "Database",
                "Port",
                "Endpoints",
                "Bundle",
                "Server",
            )
            yield table
            yield Container(id="database-service-detail")

    @property
    def table(self) -> DataTable:
        return self.query_one("#database-table", DataTable)

    def on_mount(self) -> None:
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return
        if not selection or selection.type != "root":
            self.display = False
            return
        self.display = True
        self.load()

    @on(Button.Pressed, "#refresh-databases")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.load()

    @on(DataTable.RowSelected, "#database-table")
    def handle_database_selected(self, event: DataTable.RowSelected) -> None:
        self._show_service_detail(str(event.row_key.value))

    def load(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        button = self.query_one("#refresh-databases", Button)
        button.disabled = True
        button.label = "Loading..."
        self.table.clear(columns=False)
        self._rows = []
        self._row_keys = []
        self._update_metrics()
        self._mount_detail_message("Loading database services...")

        def load_databases() -> None:
            result = describe_databases(infra)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(
            load_databases,
            thread=True,
            exclusive=True,
            group="project-databases",
        )

    def _show_result(self, result) -> None:
        if not self.selection or self.selection.type != "root":
            return
        button = self.query_one("#refresh-databases", Button)
        button.disabled = False
        button.label = "Refresh"
        self._rows = list((result.data or {}).get("rows", [])) if result.success else []
        self._populate_table(result.message)
        self._update_metrics()
        self._show_service_detail(self._row_keys[0] if self._row_keys else "")

    def _populate_table(self, empty_message: str) -> None:
        self.table.clear(columns=False)
        self._row_keys = []
        if not self._rows:
            self.table.add_row("-", "-", "-", "-", "-", "-", "-", empty_message)
            return
        for index, row in enumerate(self._rows):
            row_key = str(index)
            self._row_keys.append(row_key)
            self.table.add_row(
                str(row.get("service", "-")),
                str(row.get("engine", "-")),
                str(row.get("state", "unknown")),
                str(row.get("database", "-")),
                str(row.get("port", "-")),
                str(row.get("endpoints", "-")),
                str(row.get("bundle", "-")),
                str(row.get("server", "-")),
                key=row_key,
            )
        self.table.cursor_coordinate = (0, 0)

    def _show_service_detail(self, row_key: str) -> None:
        try:
            row = self._rows[int(row_key)]
        except (ValueError, IndexError):
            self._mount_detail_message("Select a database service to inspect settings.")
            return
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        result = build_service_ui_widget(
            infra, row.get("bundle_ref"), row.get("service_ref")
        )
        if not result.success:
            self._mount_detail_message(result.message)
            return
        widget = (result.data or {}).get("widget")
        if not isinstance(widget, Widget):
            self._mount_detail_message(
                "Selected database service returned an unexpected settings view."
            )
            return
        self._clear_detail()
        self.query_one("#database-service-detail", Container).mount(widget)

    def _mount_detail_message(self, message: str) -> None:
        self._clear_detail()
        self.query_one("#database-service-detail", Container).mount(
            Static(message, classes="service-tui-placeholder")
        )

    def _clear_detail(self) -> None:
        container = self.query_one("#database-service-detail", Container)
        for child in list(container.children):
            child.remove()

    def _update_metrics(self) -> None:
        values = [
            ("#database-metric-total", "Databases", len(self._rows), "cyan"),
            (
                "#database-metric-running",
                "Running",
                sum(1 for row in self._rows if row.get("state") == "running"),
                "green",
            ),
            (
                "#database-metric-engines",
                "Engines",
                len({row.get("engine") for row in self._rows if row.get("engine")}),
                "magenta",
            ),
            (
                "#database-metric-endpoints",
                "Endpoints",
                sum(int(row.get("endpoint_count") or 0) for row in self._rows),
                "bright_green",
            ),
        ]
        for selector, label, value, color in values:
            text = Text()
            text.append(f"{value}\n", style=f"bold {color}")
            text.append(label, style="dim")
            self.query_one(selector, Static).update(text)
