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

from mlox.application.use_cases.project import describe_secret_manager, reveal_secret

from .model import SelectionInfo


class SecretManagerPanel(Container):
    """Browse active project secret-manager keys and reveal selected values."""

    BINDINGS = [("enter", "reveal_selected", "Reveal Secret")]

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    class LoadFinished(Message):
        """Secret-manager metadata loading has finished."""

    class LoadStarted(Message):
        """Secret-manager metadata loading has started."""

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._secret_names: list[str] = []
        self._revealed: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="secret-manager-content"):
            yield Static(id="secret-manager-summary", markup=False)
            with Horizontal(id="secret-manager-browser"):
                table = DataTable(id="secret-manager-table")
                table.cursor_type = "row"
                table.add_columns("Secret Key", "Value")
                yield table
                yield Static(id="secret-manager-detail", markup=False)

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
        """Load secret-manager metadata in a worker."""

        self._secret_names = []
        self._revealed = {}
        self.table.clear(columns=False)
        self.summary.update(Panel(Text("Loading secret manager..."), title="Status"))
        self.detail.update(self._help_panel())
        self.post_message(self.LoadStarted())
        workspace = getattr(self.app, "workspace", None)

        def load_metadata() -> None:
            result = describe_secret_manager(workspace)
            self.app.call_from_thread(self._show_result, result)

        self.app.run_worker(
            load_metadata,
            thread=True,
            exclusive=True,
            group="secret-manager",
        )

    def _show_result(self, result) -> None:
        if not self.selection or self.selection.type != "root":
            self.post_message(self.LoadFinished())
            return
        if not result.success:
            self.summary.update(
                Panel(
                    Text(result.message, style="bold red"),
                    title="Secret Manager",
                    border_style="red",
                )
            )
            self.detail.update(self._help_panel())
            self.post_message(self.LoadFinished())
            return

        payload = result.data or {}
        manager = payload.get("manager", {})
        secrets = payload.get("secrets", [])
        error = payload.get("error", "")

        self.summary.update(self._manager_panel(manager, len(secrets), error))
        self._secret_names = [str(secret.get("name", "")) for secret in secrets]
        self._populate_table()
        if error:
            self.detail.update(
                Panel(
                    Text(f"Could not list secrets: {error}", style="yellow"),
                    title="Secrets",
                    border_style="yellow",
                )
            )
        elif self._secret_names:
            self.detail.update(self._help_panel())
        else:
            self.detail.update(
                Panel(
                    Text("No secrets are stored in the active manager.", style="dim"),
                    title="Secrets",
                    border_style="green",
                )
            )
        self.post_message(self.LoadFinished())

    def _populate_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        for name in self._secret_names:
            table.add_row(name, Text("hidden", style="dim"), key=name)
        if self._secret_names:
            table.cursor_coordinate = (0, 0)

    @on(DataTable.RowSelected, "#secret-manager-table")
    def handle_secret_selected(self, event: DataTable.RowSelected) -> None:
        self._reveal_secret(self._row_key_value(event.row_key))

    def action_reveal_selected(self) -> None:
        """Reveal the secret key under the table cursor."""

        row_index = self.table.cursor_row
        if row_index < 0 or row_index >= len(self._secret_names):
            return
        self._reveal_secret(self._secret_names[row_index])

    def _reveal_secret(self, name: str) -> None:
        if not name:
            return
        if name in self._revealed:
            self._show_secret_value(name, self._revealed[name])
            return

        self.detail.update(
            Panel(Text(f"Loading '{name}'..."), title=name, border_style="yellow")
        )
        workspace = getattr(self.app, "workspace", None)

        def load_value() -> None:
            result = reveal_secret(workspace, name)
            self.app.call_from_thread(self._show_secret_result, name, result)

        self.app.run_worker(
            load_value,
            thread=True,
            exclusive=True,
            group="secret-manager-value",
        )

    def _show_secret_result(self, name: str, result) -> None:
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
        self._revealed[name] = value
        self._show_secret_value(name, value)

    def _show_secret_value(self, name: str, value: Any) -> None:
        self._mark_revealed(name)
        self.detail.update(
            Panel(
                self._format_secret_value(value),
                title=name,
                border_style="green",
            )
        )

    def _mark_revealed(self, name: str) -> None:
        table = self.table
        for row_index, row in enumerate(self._secret_names):
            if row != name:
                continue
            table.update_cell_at((row_index, 1), Text("revealed", style="bold green"))
            return

    def _manager_panel(self, manager: dict, secret_count: int, error: str) -> Panel:
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column("Field", style="cyan", justify="right", no_wrap=True)
        table.add_column("Value", justify="left")
        table.add_row("Active", str(manager.get("name", "Unknown")))
        table.add_row("Kind", str(manager.get("kind", "unknown")))
        table.add_row("Status", self._status_text(str(manager.get("status", ""))))
        table.add_row("Adapter", str(manager.get("class", "-")))
        table.add_row("Secrets", str(secret_count))
        export = "yes" if manager.get("supports_keyfile_export") else "no"
        table.add_row("Keyfile export", export)
        if error:
            table.add_row("Warning", Text("secret listing failed", style="yellow"))
        return Panel(
            table,
            title="Active Secret Manager",
            border_style=self._border_style(str(manager.get("status", ""))),
        )

    def _help_panel(self) -> Panel:
        text = Text()
        text.append("Select a secret key and press Enter to reveal its value.\n")
        text.append(
            "Values are loaded on demand and never shown in the table.",
            style="dim",
        )
        return Panel(text, title="Secret Value", border_style="green")

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
        return Text(status or "unknown", style="yellow")

    def _border_style(self, status: str) -> str:
        if status == "available":
            return "green"
        if status == "unavailable":
            return "red"
        return "yellow"

    def _row_key_value(self, row_key: object) -> str:
        return str(getattr(row_key, "value", row_key))
