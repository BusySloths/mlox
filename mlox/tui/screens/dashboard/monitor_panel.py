"""Project monitor overview panel."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.monitor import describe_monitoring
from mlox.application.use_cases.services import build_service_ui_widget

from .model import SelectionInfo


class MonitorPanel(Static):
    """Root-level monitoring overview for monitor-capable services."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._rows: list[dict[str, Any]] = []
        self._row_keys: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="monitor-content"):
            with Horizontal(id="monitor-metrics"):
                yield Static(id="monitor-metric-services", classes="monitor-metric")
                yield Static(id="monitor-metric-active", classes="monitor-metric")
                yield Static(id="monitor-metric-data", classes="monitor-metric")
            with Horizontal(id="monitor-actions"):
                yield Static("Project Monitor", id="monitor-title")
                yield Button("Refresh Monitor", id="refresh-monitor")
            table = DataTable(id="monitor-table")
            table.cursor_type = "row"
            table.add_columns(
                "Bundle",
                "Server",
                "Monitor",
                "State",
                "CPU Used",
                "RAM Free",
                "Disk Free",
                "Network In",
                "Network Out",
                "Sample",
                "Message",
            )
            yield table
            yield Container(id="monitor-service-detail")

    @property
    def table(self) -> DataTable:
        return self.query_one("#monitor-table", DataTable)

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

    @on(Button.Pressed, "#refresh-monitor")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.load(refresh=True)

    @on(DataTable.RowSelected, "#monitor-table")
    def handle_monitor_selected(self, event: DataTable.RowSelected) -> None:
        self._show_service_detail(self._row_key(event))

    def load(self, refresh: bool = False) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self._set_loading(refresh)
        self.table.clear(columns=False)

        def load_monitoring() -> None:
            result = describe_monitoring(infra)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(
            load_monitoring,
            thread=True,
            exclusive=True,
            group="project-monitor",
        )

    def _show_result(self, result) -> None:
        if not self.selection or self.selection.type != "root":
            return
        self.query_one("#refresh-monitor", Button).disabled = False
        self.query_one("#refresh-monitor", Button).label = "Refresh Monitor"
        if not result.success:
            self._rows = []
            self._update_metrics()
            self.table.add_row("-", "-", "-", "-", "-", "-", "-", "-", "-", "-", result.message)
            self._mount_detail_message("Select a monitor service to inspect details.")
            return
        self._rows = list((result.data or {}).get("rows", []))
        self._populate_table()
        self._update_metrics()
        self._show_service_detail(self._row_keys[0] if self._row_keys else "")

    def _set_loading(self, refresh: bool) -> None:
        button = self.query_one("#refresh-monitor", Button)
        button.disabled = True
        button.label = "Refreshing..." if refresh else "Loading..."
        self._rows = []
        self._row_keys = []
        self._update_metrics()
        self._mount_detail_message("Loading monitor services...")

    def _populate_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        self._row_keys = []
        if not self._rows:
            table.add_row(
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "No monitor services found.",
            )
            return

        for index, row in enumerate(self._rows):
            row_key = str(index)
            self._row_keys.append(row_key)
            table.add_row(
                str(row.get("bundle", "-")),
                str(row.get("server", "-")),
                str(row.get("service", "-")),
                self._state_badge(str(row.get("state", "unknown"))),
                self._ratio_badge(row.get("cpu_used_ratio"), inverse=False),
                self._ratio_badge(row.get("ram_free_ratio"), inverse=True),
                self._ratio_badge(row.get("disk_free_ratio"), inverse=True),
                self._rate(row.get("network_in_rate"), row.get("network_unit")),
                self._rate(row.get("network_out_rate"), row.get("network_unit")),
                self._timestamp(row.get("latest_timestamp")),
                str(row.get("message") or ""),
                key=row_key,
            )
        table.cursor_coordinate = (0, 0)

    def _show_service_detail(self, row_key: str) -> None:
        row = self._row_by_key(row_key)
        bundle = row.get("bundle_ref") if row else None
        service = row.get("service_ref") if row else None
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        if not row or not bundle or not service or not infra:
            self._mount_detail_message("Select a monitor service to inspect details.")
            return

        result = build_service_ui_widget(infra, bundle, service)
        if not result.success:
            self._mount_detail_message(result.message)
            return

        widget = result.data.get("widget") if result.data else None
        if not isinstance(widget, Widget):
            self._mount_detail_message(
                "Selected monitor service returned an unexpected detail view."
            )
            return

        self._clear_detail()
        self.query_one("#monitor-service-detail", Container).mount(widget)

    def _mount_detail_message(self, message: str) -> None:
        self._clear_detail()
        self.query_one("#monitor-service-detail", Container).mount(
            Static(message, classes="service-tui-placeholder")
        )

    def _clear_detail(self) -> None:
        container = self.query_one("#monitor-service-detail", Container)
        for child in list(container.children):
            child.remove()

    def _row_by_key(self, row_key: str) -> dict[str, Any] | None:
        try:
            return self._rows[int(row_key)]
        except (ValueError, IndexError):
            return None

    def _update_metrics(self) -> None:
        services = len(self._rows)
        active = sum(1 for row in self._rows if row.get("state") == "running")
        with_data = sum(1 for row in self._rows if row.get("metric_points"))
        values = [
            ("#monitor-metric-services", "Monitor Services", services, "cyan"),
            ("#monitor-metric-active", "Running", active, "green"),
            ("#monitor-metric-data", "With Data", with_data, "bright_green"),
        ]
        for selector, label, value, color in values:
            text = Text()
            text.append(f"{value}\n", style=f"bold {color}")
            text.append(label, style="dim")
            self.query_one(selector, Static).update(text)

    def _ratio_badge(self, value: Any, *, inverse: bool) -> Text:
        if value is None:
            return Text("N/A", style="dim")
        try:
            ratio = float(value)
        except (TypeError, ValueError):
            return Text("N/A", style="dim")
        label = f"{ratio * 100:,.1f}%"
        if inverse:
            style = (
                "bold white on dark_green"
                if ratio >= 0.25
                else "bold black on bright_yellow"
                if ratio >= 0.1
                else "bold white on dark_red"
            )
        else:
            style = (
                "bold white on dark_green"
                if ratio <= 0.75
                else "bold black on bright_yellow"
                if ratio <= 0.9
                else "bold white on dark_red"
            )
        return Text(f" {label} ", style=style)

    def _state_badge(self, state: str) -> Text:
        style = {
            "running": "bold white on dark_green",
            "starting": "bold black on bright_yellow",
            "failed": "bold white on dark_red",
            "stopped": "bold white on grey23",
            "unknown": "bold white on grey23",
        }.get(state, "bold white on dark_blue")
        return Text(f" {state} ", style=style)

    def _rate(self, value: Any, unit: Any) -> str:
        if value is None:
            return "N/A"
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "N/A"
        if unit in {"By", "bytes", "byte"}:
            return f"{self._bytes(numeric)}/s"
        return f"{numeric:,.2f}{unit or ''}/s"

    def _bytes(self, value: float) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        scaled = value
        unit = units[0]
        for unit in units:
            if abs(scaled) < 1024 or unit == units[-1]:
                break
            scaled /= 1024
        return f"{scaled:,.1f} {unit}"

    def _timestamp(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        return str(value or "-")

    def _row_key(self, event: DataTable.RowSelected) -> str:
        row_key = getattr(event.row_key, "value", event.row_key)
        return str(row_key)
