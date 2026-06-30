"""Project secret-manager browser."""

from __future__ import annotations

import json
from typing import Any, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static

from mlox.application.use_cases.secrets import (
    describe_secret_managers,
    list_secret_names,
    reveal_secret,
)

from .model import SelectionInfo


class SecretManagerPanel(Container):
    """Browse project secret managers, keys, and selected secret values."""

    BINDINGS = [("enter", "reveal_selected", "Reveal Secret")]

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    class LoadFinished(Message):
        """Secret-manager metadata loading has finished."""

    class LoadStarted(Message):
        """Secret-manager metadata loading has started."""

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._managers: list[dict[str, Any]] = []
        self._manager_ids: list[str] = []
        self._selected_manager_id = ""
        self._secret_names: list[str] = []
        self._revealed: dict[tuple[str, str], Any] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="secret-manager-content"):
            yield Static(id="secret-manager-summary", markup=False)
            with Horizontal(id="secret-manager-browser"):
                manager_table = DataTable(id="secret-manager-manager-table")
                manager_table.cursor_type = "row"
                manager_table.add_columns("Manager", "Kind", "Status")
                yield manager_table

                secret_table = DataTable(id="secret-manager-table")
                secret_table.cursor_type = "row"
                secret_table.add_columns("Secret Key", "Value")
                yield secret_table

                yield Static(id="secret-manager-detail", markup=False)

    @property
    def manager_table(self) -> DataTable:
        return self.query_one("#secret-manager-manager-table", DataTable)

    @property
    def table(self) -> DataTable:
        return self.query_one("#secret-manager-table", DataTable)

    @property
    def summary(self) -> Static:
        return self.query_one("#secret-manager-summary", Static)

    @property
    def detail(self) -> Static:
        return self.query_one("#secret-manager-detail", Static)

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
        """Load secret-manager metadata without listing secret keys."""

        self._reset_state()
        self.summary.update(Panel(Text("Loading secret managers..."), title="Status"))
        self.detail.update(self._help_panel())
        self.post_message(self.LoadStarted())
        workspace = getattr(self.app, "workspace", None)

        def load_metadata() -> None:
            result = describe_secret_managers(workspace)
            self.app.call_from_thread(self._show_managers_result, result)

        self.app.run_worker(
            load_metadata,
            thread=True,
            exclusive=True,
            group="secret-manager",
        )

    def _reset_state(self) -> None:
        self._managers = []
        self._manager_ids = []
        self._selected_manager_id = ""
        self._secret_names = []
        self._revealed = {}
        self.manager_table.clear(columns=False)
        self.table.clear(columns=False)

    def _show_managers_result(self, result) -> None:
        if not self.selection or self.selection.type != "root":
            self.post_message(self.LoadFinished())
            return
        if not result.success:
            self.summary.update(
                Panel(
                    Text(result.message, style="bold red"),
                    title="Secret Managers",
                    border_style="red",
                )
            )
            self.detail.update(self._help_panel())
            self.post_message(self.LoadFinished())
            return

        payload = result.data or {}
        self._managers = list(payload.get("managers", []))
        self._populate_manager_table()
        self.summary.update(self._summary_panel())

        active_manager_id = str(payload.get("active_manager_id") or "")
        if active_manager_id:
            self._select_manager(active_manager_id)
        else:
            self.detail.update(
                Panel(
                    Text("No secret managers are available.", style="dim"),
                    title="Secret Managers",
                    border_style="yellow",
                )
            )
            self.post_message(self.LoadFinished())

    def _populate_manager_table(self) -> None:
        table = self.manager_table
        table.clear(columns=False)
        self._manager_ids = []
        for manager in self._managers:
            manager_id = str(manager.get("id", ""))
            if not manager_id:
                continue
            self._manager_ids.append(manager_id)
            table.add_row(
                self._manager_name(manager),
                str(manager.get("kind", "unknown")),
                self._status_text(str(manager.get("status", ""))),
                key=manager_id,
            )

    def _select_manager(self, manager_id: str) -> None:
        if manager_id not in self._manager_ids:
            return
        self._selected_manager_id = manager_id
        self._secret_names = []
        self.table.clear(columns=False)
        self.detail.update(
            Panel(
                Text("Loading secret keys..."),
                title="Secrets",
                border_style="yellow",
            )
        )
        self._mark_selected_manager(manager_id)
        workspace = getattr(self.app, "workspace", None)

        def load_keys() -> None:
            result = list_secret_names(workspace, manager_id)
            self.app.call_from_thread(self._show_secrets_result, manager_id, result)

        self.app.run_worker(
            load_keys,
            thread=True,
            exclusive=True,
            group="secret-manager-secrets",
        )

    def _show_secrets_result(self, manager_id: str, result) -> None:
        if manager_id != self._selected_manager_id:
            return
        if not self.selection or self.selection.type != "root":
            return
        if not result.success:
            self.detail.update(
                Panel(
                    Text(result.message, style="bold red"),
                    title=self._selected_manager_name(),
                    border_style="red",
                )
            )
            return

        payload = result.data or {}
        secrets = list(payload.get("secrets", []))
        self._secret_names = [str(secret.get("name", "")) for secret in secrets]
        self._populate_secret_table()
        if self._secret_names:
            self.detail.update(self._help_panel())
        else:
            self.detail.update(
                Panel(
                    Text(
                        "This secret manager does not contain any secrets.",
                        style="dim",
                    ),
                    title=self._selected_manager_name(),
                    border_style="green",
                )
            )
        self.post_message(self.LoadFinished())

    def _populate_secret_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        for name in self._secret_names:
            table.add_row(name, Text("hidden", style="dim"), key=name)
        if self._secret_names:
            table.cursor_coordinate = (0, 0)

    @on(DataTable.RowSelected, "#secret-manager-manager-table")
    def handle_manager_selected(self, event: DataTable.RowSelected) -> None:
        self._select_manager(self._row_key_value(event.row_key))

    @on(DataTable.RowSelected, "#secret-manager-table")
    def handle_secret_selected(self, event: DataTable.RowSelected) -> None:
        self._reveal_secret(self._row_key_value(event.row_key))

    def action_reveal_selected(self) -> None:
        """Reveal the secret key under the secret table cursor."""

        row_index = self.table.cursor_row
        if row_index < 0 or row_index >= len(self._secret_names):
            return
        self._reveal_secret(self._secret_names[row_index])

    def _reveal_secret(self, name: str) -> None:
        manager_id = self._selected_manager_id
        if not manager_id or not name:
            return
        cache_key = (manager_id, name)
        if cache_key in self._revealed:
            self._show_secret_value(name, self._revealed[cache_key])
            return

        self.detail.update(
            Panel(Text(f"Loading '{name}'..."), title=name, border_style="yellow")
        )
        workspace = getattr(self.app, "workspace", None)

        def load_value() -> None:
            result = reveal_secret(workspace, manager_id, name)
            self.app.call_from_thread(
                self._show_secret_result,
                manager_id,
                name,
                result,
            )

        self.app.run_worker(
            load_value,
            thread=True,
            exclusive=True,
            group="secret-manager-value",
        )

    def _show_secret_result(self, manager_id: str, name: str, result) -> None:
        if manager_id != self._selected_manager_id:
            return
        if not self.selection or self.selection.type != "root":
            return
        if not result.success:
            self.detail.update(
                Panel(
                    Text(result.message, style="bold red"),
                    title=name,
                    border_style="red",
                )
            )
            return
        value = (result.data or {}).get("value")
        self._revealed[(manager_id, name)] = value
        self._show_secret_value(name, value)

    def _show_secret_value(self, name: str, value: Any) -> None:
        self._mark_revealed(name)
        self.detail.update(
            Panel(
                self._format_secret_value(value),
                title=f"{self._selected_manager_name()} / {name}",
                border_style="green",
            )
        )

    def _summary_panel(self) -> Panel:
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column("Field", style="cyan", justify="right", no_wrap=True)
        table.add_column("Value", justify="left")
        table.add_row("Managers", str(len(self._managers)))
        table.add_row("Active", self._selected_manager_name() or "-")
        table.add_row("Available", str(self._count_available_managers()))
        table.add_row("Services", str(self._count_service_managers()))
        return Panel(table, title="Project Secret Managers", border_style="green")

    def _help_panel(self) -> Panel:
        text = Text()
        text.append("Select a manager to load its secret keys.\n")
        text.append("Select a secret key and press Enter to reveal its value.\n")
        text.append(
            "Values are loaded on demand and never shown in the table.",
            style="dim",
        )
        return Panel(text, title="Secret Value", border_style="green")

    def _mark_selected_manager(self, manager_id: str) -> None:
        self.summary.update(self._summary_panel())
        index = self._manager_ids.index(manager_id)
        self.manager_table.cursor_coordinate = (index, 0)

    def _mark_revealed(self, name: str) -> None:
        for row_index, row in enumerate(self._secret_names):
            if row != name:
                continue
            self.table.update_cell_at(
                (row_index, 1),
                Text("revealed", style="bold green"),
            )
            return

    def _manager_name(self, manager: dict[str, Any]) -> Text:
        name = str(manager.get("name", "Unknown"))
        text = Text(name)
        if manager.get("is_active"):
            text.append(" active", style="bold green")
        return text

    def _selected_manager_name(self) -> str:
        for manager in self._managers:
            if manager.get("id") == self._selected_manager_id:
                return str(manager.get("name", "Unknown"))
        return ""

    def _count_available_managers(self) -> int:
        return sum(
            1 for manager in self._managers if manager.get("is_available") is True
        )

    def _count_service_managers(self) -> int:
        return sum(1 for manager in self._managers if manager.get("kind") == "service")

    def _format_secret_value(self, value: Any) -> Text:
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, indent=2, sort_keys=True, default=str)
        else:
            rendered = str(value)
        return Text(rendered)

    def _status_text(self, status: str) -> Text:
        if status == "available":
            return Text("available", style="bold green")
        if status == "unavailable":
            return Text("unavailable", style="bold red")
        return Text(status or "not checked", style="yellow")

    def _row_key_value(self, row_key: object) -> str:
        return str(getattr(row_key, "value", row_key))
