"""Project firewall management panel."""

from __future__ import annotations

from typing import Any, Optional

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.renderables.digits import Digits as DigitsRenderable
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static, TextArea

from mlox.application.use_cases.firewall import (
    describe_project_firewalls,
    disable_bundle_firewall,
    enable_bundle_firewall_with_options,
)

from .model import SelectionInfo


class EnableFirewallDialog(ModalScreen[dict[str, list[int] | list[str]] | None]):
    """Collect firewall enable options before applying default-drop rules."""

    def __init__(self, bundle_name: str, recommended_ports: list[int]) -> None:
        super().__init__()
        self.bundle_name = bundle_name
        self.recommended_ports = recommended_ports

    def compose(self) -> ComposeResult:
        with Container(id="enable-firewall-dialog"):
            yield Label("Enable Firewall", id="enable-firewall-title")
            yield Static(
                (
                    f"{self.bundle_name}: recommended ports "
                    f"{self._format_ports(self.recommended_ports)}. "
                    "SSH is required and cannot be excluded."
                ),
                id="enable-firewall-help",
            )
            yield Static("", id="enable-firewall-error")
            yield Label("Additional ports", classes="firewall-dialog-label")
            yield Input(
                placeholder="8080, 9000",
                id="enable-firewall-custom-ports",
            )
            yield Label("Exclude recommended ports", classes="firewall-dialog-label")
            yield Input(
                placeholder="5000",
                id="enable-firewall-exclude-ports",
            )
            yield Label(
                "Source whitelist for all open ports",
                classes="firewall-dialog-label",
            )
            yield Input(
                placeholder="203.0.113.10, 203.0.113.0/24",
                id="enable-firewall-source-ips",
            )
            with Horizontal(id="enable-firewall-dialog-actions"):
                yield Button("Cancel", id="cancel-enable-firewall")
                yield Button(
                    "Enable Firewall",
                    id="confirm-enable-firewall",
                    variant="success",
                )

    def on_mount(self) -> None:
        self.query_one("#enable-firewall-custom-ports", Input).focus()

    @on(Button.Pressed, "#cancel-enable-firewall")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-enable-firewall")
    def handle_confirm(self, _: Button.Pressed) -> None:
        try:
            custom_ports = self._parse_ports("#enable-firewall-custom-ports")
            exclude_ports = self._parse_ports("#enable-firewall-exclude-ports")
        except ValueError as exc:
            self.query_one("#enable-firewall-error", Static).update(str(exc))
            return

        source_ips = self._parse_csv("#enable-firewall-source-ips")
        self.dismiss(
            {
                "custom_ports": custom_ports,
                "exclude_ports": exclude_ports,
                "source_ips": source_ips,
            }
        )

    def _parse_ports(self, selector: str) -> list[int]:
        ports = []
        for value in self._parse_csv(selector):
            try:
                port = int(value)
            except ValueError as exc:
                raise ValueError(f"Invalid port: {value}") from exc
            if port < 1 or port > 65535:
                raise ValueError(f"Port out of range: {port}")
            ports.append(port)
        return sorted(set(ports))

    def _parse_csv(self, selector: str) -> list[str]:
        value = self.query_one(selector, Input).value
        return [part.strip() for part in value.split(",") if part.strip()]

    def _format_ports(self, ports: list[int]) -> str:
        return ", ".join(str(port) for port in ports) or "none"


class FirewallPanel(Static):
    """Project-level firewall inventory and bundle firewall controls."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._rows: list[dict[str, Any]] = []
        self._row_ids: list[str] = []
        self._selected_id = ""
        self._loading = False

    def compose(self) -> ComposeResult:
        with Vertical(id="firewall-content"):
            yield Static(id="firewall-summary", markup=False)
            with Horizontal(id="firewall-actions"):
                yield Button("Refresh", id="refresh-firewalls", variant="primary")
                yield Button("Enable Firewall", id="enable-firewall", variant="success")
                yield Button("Disable Firewall", id="disable-firewall", variant="error")
            with Horizontal(id="firewall-browser"):
                table = DataTable(id="firewall-table")
                table.cursor_type = "row"
                table.add_columns(
                    "Bundle",
                    "Server",
                    "Firewall",
                )
                yield table
                with Vertical(id="firewall-detail-pane"):
                    yield Static(id="firewall-detail", markup=False)
                    yield TextArea("", id="firewall-raw-status")

    @property
    def table(self) -> DataTable:
        return self.query_one("#firewall-table", DataTable)

    @property
    def summary(self) -> Static:
        return self.query_one("#firewall-summary", Static)

    @property
    def detail(self) -> Static:
        return self.query_one("#firewall-detail", Static)

    @property
    def raw_status(self) -> TextArea:
        return self.query_one("#firewall-raw-status", TextArea)

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

    def load(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        infra = getattr(workspace, "infrastructure", None)
        self._set_loading(True)
        self.summary.update(Panel(Text("Loading firewall status..."), title="Firewall"))
        self.detail.update(self._help_panel())
        self._show_raw_status("")

        def load_firewalls() -> None:
            result = describe_project_firewalls(infra)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(
            load_firewalls,
            thread=True,
            exclusive=True,
            group="firewall-status",
        )

    def _show_result(self, result) -> None:
        self._set_loading(False)
        if not self.selection or self.selection.type != "root":
            return
        if not result.success:
            self.summary.update(
                Panel(Text(result.message, style="bold red"), title="Firewall")
            )
            return

        payload = result.data or {}
        self._rows = list(payload.get("rows", []))
        self._populate_table()
        self.summary.update(self._summary_panel(payload.get("summary", {})))
        if self._row_ids:
            self._select_row(self._row_ids[0])
        else:
            self.detail.update(
                Panel(
                    Text("No firewall-capable servers detected.", style="dim"),
                    title="Firewall",
                    border_style="yellow",
                )
            )
        self._update_action_state()

    def _populate_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        self._row_ids = []
        for row in self._rows:
            row_id = str(row.get("id") or row.get("bundle") or "")
            if not row_id:
                continue
            self._row_ids.append(row_id)
            table.add_row(
                str(row.get("bundle", "-")),
                str(row.get("server", "-")),
                self._firewall_badge(row),
                key=row_id,
            )
        if self._row_ids:
            table.cursor_coordinate = (0, 0)

    @on(DataTable.RowSelected, "#firewall-table")
    def handle_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = getattr(event.row_key, "value", event.row_key)
        self._select_row(str(row_key))

    @on(Button.Pressed, "#refresh-firewalls")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.load()

    @on(Button.Pressed, "#enable-firewall")
    def handle_enable(self, _: Button.Pressed) -> None:
        row = self._selected_row()
        if not row:
            self.notify("Select a firewall-capable bundle.", severity="warning")
            return
        self.app.push_screen(
            EnableFirewallDialog(
                str(row.get("bundle", "-")),
                list(row.get("recommended_ports", []) or []),
            ),
            lambda values: self._enable_firewall_from_dialog(row, values),
        )

    def _enable_firewall_from_dialog(
        self,
        row: dict[str, Any],
        values: dict[str, list[int] | list[str]] | None,
    ) -> None:
        if values is None:
            return
        self._run_bundle_action(
            lambda: enable_bundle_firewall_with_options(
                row["bundle_ref"],
                custom_ports=values.get("custom_ports", []),
                exclude_ports=values.get("exclude_ports", []),
                source_ips=values.get("source_ips", []),
            ),
            "firewall-enable",
        )

    @on(Button.Pressed, "#disable-firewall")
    def handle_disable(self, _: Button.Pressed) -> None:
        row = self._selected_row()
        if not row:
            self.notify("Select a firewall-capable bundle.", severity="warning")
            return
        self._run_bundle_action(
            lambda: disable_bundle_firewall(row["bundle_ref"]),
            "firewall-disable",
        )

    def _run_bundle_action(self, operation, group: str) -> None:
        self._set_loading(True)

        def run() -> None:
            result = operation()
            self.app.call_from_thread(self._finish_bundle_action, result)

        self.app.run_worker(run, thread=True, exclusive=True, group=group)

    def _finish_bundle_action(self, result) -> None:
        self._set_loading(False)
        if not result.success:
            self.notify(result.message, severity="error")
            self.load()
            return
        self.notify(result.message)
        self.load()

    def _select_row(self, row_id: str) -> None:
        self._selected_id = row_id
        row = self._selected_row()
        self.detail.update(self._detail_panel(row) if row else self._help_panel())
        self._show_raw_status(str(row.get("raw_status") or "") if row else "")
        self._update_action_state()

    def _selected_row(self) -> dict[str, Any] | None:
        for row in self._rows:
            if str(row.get("id") or row.get("bundle") or "") == self._selected_id:
                return row
        return None

    def _summary_panel(self, summary: dict[str, Any]) -> Group:
        metrics = [
            Panel(
                DigitsRenderable(str(summary.get("capable", 0))),
                title="Capable",
                border_style="cyan",
            ),
            Panel(
                DigitsRenderable(str(summary.get("active", 0))),
                title="Active",
                border_style="green",
            ),
            Panel(
                DigitsRenderable(str(summary.get("inactive", 0))),
                title="Inactive",
                border_style="yellow",
            ),
        ]
        return Group(Columns(metrics, expand=True, equal=True))

    def _detail_panel(self, row: dict[str, Any]) -> Panel:
        layout = Table.grid(expand=True)
        layout.add_column(justify="right", style="cyan", no_wrap=True)
        layout.add_column(ratio=3)
        layout.add_row("Bundle", str(row.get("bundle", "-")))
        layout.add_row("Server", str(row.get("server", "-")))
        layout.add_row("Firewall", self._firewall_badge(row))
        layout.add_row(
            "Open Ports",
            self._ports_text(row.get("open_ports", []), row.get("open_ports_unknown")),
        )
        layout.add_row(
            "Recommended",
            self._ports_text(row.get("recommended_ports", []), False),
        )
        error = str(row.get("status_error") or "")
        if error:
            layout.add_row("Status Error", Text(error, style="bold red"))
        layout.add_row("Port Details", self._port_table(row))
        return Panel(
            layout,
            title=f"Firewall: {row.get('bundle', '-')}",
            border_style="green" if row.get("is_active") else "yellow",
        )

    def _port_table(self, row: dict[str, Any]) -> Table:
        open_ports = set(row.get("open_ports", []) or [])
        source_by_port = row.get("source_by_port", {}) or {}
        table = Table(show_header=True, header_style="bold", expand=True)
        table.add_column("Port", justify="right")
        table.add_column("Service")
        table.add_column("Name")
        table.add_column("Open")
        table.add_column("Sources")
        for port_row in row.get("recommended_rows", []) or []:
            port = int(port_row["port"])
            table.add_row(
                str(port),
                str(port_row.get("service", "-")),
                str(port_row.get("name", "-")),
                "yes" if port in open_ports else "no",
                ", ".join(source_by_port.get(port, [])) or "any",
            )
        if not (row.get("recommended_rows", []) or []):
            table.add_row("-", "-", "-", "-", "-")
        return table

    def _help_panel(self) -> Panel:
        return Panel(
            Text(
                "Select a firewall-capable bundle to inspect open ports. "
                "Enabling the firewall uses the recommended ports and always "
                "includes SSH to avoid locking out remote access."
            ),
            title="Firewall",
            border_style="cyan",
        )

    def _firewall_badge(self, row: dict[str, Any]) -> Text:
        if row.get("status_error"):
            return Text(" Error ", style="bold white on dark_red")
        if row.get("is_active"):
            return Text(" Active ", style="bold white on dark_green")
        return Text(" Inactive ", style="bold black on bright_yellow")

    def _ports_text(self, ports: object, unknown: object = False) -> Text:
        if unknown:
            return Text("unknown", style="yellow")
        values = [str(port) for port in ports or []]
        if not values:
            return Text("none", style="dim")
        return Text(", ".join(values))

    def _show_raw_status(self, raw_status: str) -> None:
        if not self.is_mounted:
            return
        editor = self.raw_status
        editor.text = raw_status
        editor.display = bool(raw_status)
        editor.border_title = "Raw Status"

    def _set_loading(self, loading: bool) -> None:
        self._loading = loading
        self._update_action_state()

    def _update_action_state(self) -> None:
        if not self.is_mounted:
            return
        selected = self._selected_row()
        for button in self.query(Button):
            button.disabled = self._loading
        if selected is None:
            self.query_one("#enable-firewall", Button).disabled = True
            self.query_one("#disable-firewall", Button).disabled = True
            return
        self.query_one("#enable-firewall", Button).disabled = (
            self._loading or bool(selected.get("is_active"))
        )
        self.query_one("#disable-firewall", Button).disabled = (
            self._loading or not bool(selected.get("is_active"))
        )
