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
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static, TextArea

from mlox.application.use_cases.secrets import (
    activate_secret_manager,
    collect_service_secrets,
    describe_secret_managers,
    list_secret_names,
    reveal_secret,
    save_secret,
)

from .model import SelectionInfo


class SecretEditDialog(ModalScreen[tuple[str, Any] | None]):
    """Modal prompt for creating or updating one secret."""

    def __init__(
        self,
        *,
        title: str,
        key: str = "",
        value: Any = "",
        key_editable: bool = True,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.key = key
        self.value = value
        self.key_editable = key_editable

    def compose(self) -> ComposeResult:
        with Container(id="secret-edit-dialog"):
            yield Label(self.title_text, id="secret-edit-title")
            yield Static(
                "Use JSON for objects and arrays. Non-JSON input is stored as text.",
                id="secret-edit-help",
            )
            yield Static("", id="secret-edit-error")
            yield Input(
                value=self.key,
                placeholder="secret-key",
                id="secret-edit-key",
            )
            yield TextArea(
                self._format_initial_value(),
                id="secret-edit-value",
            )
            with Horizontal(id="secret-edit-actions"):
                yield Button("Cancel", id="cancel-secret-edit")
                yield Button(
                    "Save Secret",
                    id="confirm-secret-edit",
                    variant="success",
                )

    def on_mount(self) -> None:
        key_input = self.query_one("#secret-edit-key", Input)
        key_input.disabled = not self.key_editable
        if self.key_editable:
            key_input.focus()
            return
        self.query_one("#secret-edit-value", TextArea).focus()

    @on(Input.Submitted, "#secret-edit-key")
    def handle_key_submitted(self, _: Input.Submitted) -> None:
        self.query_one("#secret-edit-value", TextArea).focus()

    @on(Button.Pressed, "#cancel-secret-edit")
    def handle_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm-secret-edit")
    def handle_confirm(self, _: Button.Pressed) -> None:
        self._dismiss_with_secret()

    def _dismiss_with_secret(self) -> None:
        key = self.query_one("#secret-edit-key", Input).value.strip()
        if not key:
            self.query_one("#secret-edit-error", Static).update(
                "Secret key is required."
            )
            return
        raw_value = self.query_one("#secret-edit-value", TextArea).text
        self.dismiss((key, self._parse_value(raw_value)))

    def _format_initial_value(self) -> str:
        if isinstance(self.value, (dict, list)):
            return json.dumps(self.value, indent=2, sort_keys=True, default=str)
        return str(self.value)

    def _parse_value(self, value: str) -> Any:
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value


class SecretManagerPanel(Container):
    """Browse project secret managers, keys, and selected secret values."""

    BINDINGS = [("enter", "reveal_selected", "Reveal Secret")]

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    class LoadFinished(Message):
        """Secret-manager metadata loading has finished."""

    class LoadStarted(Message):
        """Secret-manager metadata loading has started."""

    class ActiveManagerChanged(Message):
        """The active project secret manager changed."""

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._managers: list[dict[str, Any]] = []
        self._manager_ids: list[str] = []
        self._selected_manager_id = ""
        self._secret_names: list[str] = []
        self._revealed: dict[tuple[str, str], Any] = {}
        self._displayed_secret: tuple[str, str] | None = None
        self._collecting_service_secrets = False

    def compose(self) -> ComposeResult:
        with Vertical(id="secret-manager-content"):
            yield Static(id="secret-manager-summary", markup=False)
            with Horizontal(id="secret-manager-actions"):
                yield Button("Add Secret", id="add-secret", variant="success")
                yield Button("Update", id="update-secret")
                yield Button("Copy Secret", id="copy-secret")
                yield Button(
                    "Collect Service Secrets",
                    id="collect-service-secrets",
                    variant="primary",
                )
                yield Button(
                    "Use Selected as Active",
                    id="activate-secret-manager",
                    variant="warning",
                )
            with Horizontal(id="secret-manager-browser"):
                manager_table = DataTable(id="secret-manager-manager-table")
                manager_table.cursor_type = "row"
                manager_table.add_columns("Manager")
                yield manager_table

                secret_table = DataTable(id="secret-manager-table")
                secret_table.cursor_type = "row"
                secret_table.add_columns("Secret Key", "Value")
                yield secret_table

                with Vertical(id="secret-manager-detail-pane"):
                    yield Static(id="secret-manager-detail", markup=False)
                    yield TextArea("", id="secret-manager-detail-editor")

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

    @property
    def detail_editor(self) -> TextArea:
        return self.query_one("#secret-manager-detail-editor", TextArea)

    def on_mount(self) -> None:
        self.detail_editor.display = False
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
        self._show_detail_panel(self._help_panel())
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
        self._displayed_secret = None
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
            self._show_detail_panel(self._help_panel())
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
            self._show_detail_panel(
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
                key=manager_id,
            )

    def _select_manager(self, manager_id: str) -> None:
        if manager_id not in self._manager_ids:
            return
        self._selected_manager_id = manager_id
        self._secret_names = []
        self.table.clear(columns=False)
        self._update_action_state()
        self._show_detail_panel(
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
            self._show_detail_panel(
                Panel(
                    Text(result.message, style="bold red"),
                    title=self._selected_manager_name(),
                    border_style="red",
                )
            )
            self.post_message(self.LoadFinished())
            self._update_action_state()
            return

        payload = result.data or {}
        secrets = list(payload.get("secrets", []))
        self._secret_names = [str(secret.get("name", "")) for secret in secrets]
        self._populate_secret_table()
        if self._secret_names:
            self._show_detail_panel(self._help_panel())
        else:
            self._show_detail_panel(
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
        self._update_action_state()

    def _populate_secret_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        for name in self._secret_names:
            table.add_row(name, Text("hidden", style="dim"), key=name)
        if self._secret_names:
            table.cursor_coordinate = (0, 0)
        self._update_action_state()

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

    def can_activate_selected_manager(self) -> bool:
        manager = self._selected_manager()
        if not manager:
            return False
        if manager.get("is_active"):
            return False
        if manager.get("is_available") is False:
            return False
        return bool(self._selected_manager_id)

    def action_activate_selected_manager(self) -> None:
        manager_id = self._selected_manager_id
        if not manager_id:
            return
        workspace = getattr(self.app, "workspace", None)
        self._show_detail_panel(
            Panel(
                Text("Changing active secret manager..."),
                title=self._selected_manager_name(),
                border_style="yellow",
            )
        )

        def activate() -> None:
            result = activate_secret_manager(workspace, manager_id)
            self.app.call_from_thread(self._show_activation_result, result)

        self.app.run_worker(
            activate,
            thread=True,
            exclusive=True,
            group="secret-manager-activate",
        )

    @on(Button.Pressed, "#activate-secret-manager")
    def handle_activate_pressed(self, _: Button.Pressed) -> None:
        self.action_activate_selected_manager()

    @on(Button.Pressed, "#collect-service-secrets")
    def handle_collect_service_secrets_pressed(self, _: Button.Pressed) -> None:
        self._collect_service_secrets()

    @on(Button.Pressed, "#add-secret")
    def handle_add_pressed(self, _: Button.Pressed) -> None:
        self._open_secret_dialog(
            title="Add Secret",
            key="",
            value="",
            key_editable=True,
        )

    @on(Button.Pressed, "#update-secret")
    def handle_edit_pressed(self, _: Button.Pressed) -> None:
        name = self._selected_secret_name()
        if not name:
            return
        cache_key = (self._selected_manager_id, name)
        if self._displayed_secret == cache_key and self.detail_editor.display:
            self._save_secret(name, self._parse_secret_text(self.detail_editor.text))
            return
        if cache_key in self._revealed:
            self._show_secret_value(name, self._revealed[cache_key])
            self.detail_editor.focus()
            return
        self._load_secret_for_edit(name)

    @on(Button.Pressed, "#copy-secret")
    def handle_copy_secret_pressed(self, _: Button.Pressed) -> None:
        self._copy_selected_secret()

    def _reveal_secret(self, name: str) -> None:
        manager_id = self._selected_manager_id
        if not manager_id or not name:
            return
        cache_key = (manager_id, name)
        if cache_key in self._revealed:
            self._show_secret_value(name, self._revealed[cache_key])
            return

        self._show_detail_panel(
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

    def _load_secret_for_edit(self, name: str) -> None:
        manager_id = self._selected_manager_id
        if not manager_id:
            return
        self._show_detail_panel(
            Panel(
                Text(f"Loading '{name}' for edit..."),
                title=name,
                border_style="yellow",
            )
        )
        workspace = getattr(self.app, "workspace", None)

        def load_value() -> None:
            result = reveal_secret(workspace, manager_id, name)
            self.app.call_from_thread(
                self._open_edit_dialog_from_result,
                manager_id,
                name,
                result,
            )

        self.app.run_worker(
            load_value,
            thread=True,
            exclusive=True,
            group="secret-manager-edit",
        )

    def _copy_selected_secret(self) -> None:
        name = self._selected_secret_name()
        manager_id = self._selected_manager_id
        if not manager_id or not name:
            self.notify("No secret selected.", severity="warning")
            return

        cache_key = (manager_id, name)
        if self._displayed_secret == cache_key and self.detail_editor.display:
            self._copy_secret_text(name, self.detail_editor.text)
            return
        if cache_key in self._revealed:
            self._copy_secret_value(name, self._revealed[cache_key])
            return

        self._show_detail_panel(
            Panel(
                Text(f"Loading '{name}' for copy..."),
                title=name,
                border_style="yellow",
            )
        )
        workspace = getattr(self.app, "workspace", None)

        def load_value() -> None:
            result = reveal_secret(workspace, manager_id, name)
            self.app.call_from_thread(
                self._copy_secret_from_result,
                manager_id,
                name,
                result,
            )

        self.app.run_worker(
            load_value,
            thread=True,
            exclusive=True,
            group="secret-manager-copy",
        )

    def _show_secret_result(self, manager_id: str, name: str, result) -> None:
        if manager_id != self._selected_manager_id:
            return
        if not self.selection or self.selection.type != "root":
            return
        if not result.success:
            self._show_detail_panel(
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

    def _open_edit_dialog_from_result(self, manager_id: str, name: str, result) -> None:
        if manager_id != self._selected_manager_id:
            return
        if not result.success:
            self._show_secret_result(manager_id, name, result)
            return
        value = (result.data or {}).get("value")
        self._revealed[(manager_id, name)] = value
        self._show_secret_value(name, value)
        self.detail_editor.focus()

    def _copy_secret_from_result(self, manager_id: str, name: str, result) -> None:
        if manager_id != self._selected_manager_id:
            return
        if not result.success:
            self._show_secret_result(manager_id, name, result)
            return
        value = (result.data or {}).get("value")
        self._revealed[(manager_id, name)] = value
        self._show_secret_value(name, value)
        self._copy_secret_value(name, value)

    def _copy_secret_value(self, name: str, value: Any) -> None:
        self._copy_secret_text(name, self._format_secret_value(value))

    def _copy_secret_text(self, name: str, text: str) -> None:
        self.app.copy_to_clipboard(text)
        self.notify(f"Copied secret '{name}'.")

    def _open_secret_dialog(
        self,
        *,
        title: str,
        key: str,
        value: Any,
        key_editable: bool,
    ) -> None:
        if not self._selected_manager_id:
            return

        def save_from_dialog(secret: tuple[str, Any] | None) -> None:
            if secret is None:
                return
            name, secret_value = secret
            self._save_secret(name, secret_value)

        self.app.push_screen(
            SecretEditDialog(
                title=title,
                key=key,
                value=value,
                key_editable=key_editable,
            ),
            save_from_dialog,
        )

    def _save_secret(self, name: str, value: Any) -> None:
        manager_id = self._selected_manager_id
        if not manager_id:
            return
        self._show_detail_panel(
            Panel(Text(f"Saving '{name}'..."), title=name, border_style="yellow")
        )
        workspace = getattr(self.app, "workspace", None)

        def save_value() -> None:
            result = save_secret(workspace, manager_id, name, value)
            self.app.call_from_thread(
                self._show_save_result,
                manager_id,
                name,
                result,
            )

        self.app.run_worker(
            save_value,
            thread=True,
            exclusive=True,
            group="secret-manager-save",
        )

    def _collect_service_secrets(self) -> None:
        manager_id = self._selected_manager_id
        if not manager_id:
            return
        self._collecting_service_secrets = True
        self._update_action_state()
        self._show_detail_panel(
            Panel(
                Text("Collecting service secrets..."),
                title=self._selected_manager_name(),
                border_style="yellow",
            )
        )
        workspace = getattr(self.app, "workspace", None)

        def collect() -> None:
            result = collect_service_secrets(workspace, manager_id)
            self.app.call_from_thread(
                self._show_collect_service_secrets_result,
                manager_id,
                result,
            )

        self.app.run_worker(
            collect,
            thread=True,
            exclusive=True,
            group="secret-manager-collect",
        )

    def _show_collect_service_secrets_result(self, manager_id: str, result) -> None:
        self._collecting_service_secrets = False
        self._update_action_state()
        if manager_id != self._selected_manager_id:
            return
        if not result.success:
            self._show_detail_panel(
                Panel(
                    Text(result.message, style="bold red"),
                    title=self._selected_manager_name(),
                    border_style="red",
                )
            )
            return
        self.notify(result.message)
        self._revealed = {
            key: value
            for key, value in self._revealed.items()
            if key[0] != manager_id
        }
        self._select_manager(manager_id)

    def _show_save_result(self, manager_id: str, name: str, result) -> None:
        if manager_id != self._selected_manager_id:
            return
        if not result.success:
            self._show_detail_panel(
                Panel(
                    Text(result.message, style="bold red"),
                    title=name,
                    border_style="red",
                )
            )
            return
        value = (result.data or {}).get("value")
        self._revealed[(manager_id, name)] = value
        if name not in self._secret_names:
            self._secret_names.append(name)
            self._secret_names.sort()
            self._populate_secret_table()
        self._show_secret_value(name, value)

    def _show_activation_result(self, result) -> None:
        if not result.success:
            self._show_detail_panel(
                Panel(
                    Text(result.message, style="bold red"),
                    title="Active Secret Manager",
                    border_style="red",
                )
            )
            return
        self.notify(result.message)
        self.post_message(self.ActiveManagerChanged())
        self.load()

    def _show_secret_value(self, name: str, value: Any) -> None:
        self._mark_revealed(name)
        self._displayed_secret = (self._selected_manager_id, name)
        self.detail.display = False
        editor = self.detail_editor
        editor.display = True
        editor.border_title = f"{self._selected_manager_name()} / {name}"
        editor.border_subtitle = "Edit text, then press Update to save"
        editor.load_text(self._format_secret_value(value))

    def _show_detail_panel(self, panel: Panel) -> None:
        self._displayed_secret = None
        self.detail_editor.display = False
        self.detail.display = True
        self.detail.update(panel)

    def _parse_secret_text(self, value: str) -> Any:
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value

    def _summary_panel(self) -> Panel:
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column("Field", style="cyan", justify="right", no_wrap=True)
        table.add_column("Value", justify="left")
        table.add_row("Managers", str(len(self._managers)))
        table.add_row("Active", self._selected_manager_name() or "-")
        table.add_row("Bundle", self._selected_location_field("bundle"))
        table.add_row("Backend", self._selected_location_field("backend"))
        table.add_row("Service", self._selected_location_field("service"))
        table.add_row("Adapter", self._selected_manager_field("class"))
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

    def _location_field(self, manager: dict[str, Any], field: str) -> str:
        location = manager.get("location", {})
        if not isinstance(location, dict):
            return "-"
        return str(location.get(field, "-") or "-")

    def _selected_location_field(self, field: str) -> str:
        manager = self._selected_manager()
        return self._location_field(manager, field) if manager else "-"

    def _selected_manager_name(self) -> str:
        manager = self._selected_manager()
        return str(manager.get("name", "Unknown")) if manager else ""

    def _selected_manager_field(self, field: str) -> str:
        manager = self._selected_manager()
        return str(manager.get(field, "-") or "-") if manager else "-"

    def _selected_manager(self) -> dict[str, Any] | None:
        for manager in self._managers:
            if manager.get("id") == self._selected_manager_id:
                return manager
        return None

    def _selected_secret_name(self) -> str:
        row_index = self.table.cursor_row
        if row_index < 0 or row_index >= len(self._secret_names):
            return ""
        return self._secret_names[row_index]

    def _update_action_state(self) -> None:
        if not self.is_mounted:
            return
        has_manager = bool(self._selected_manager_id)
        has_secret = bool(self._secret_names)
        self.query_one("#add-secret", Button).disabled = not has_manager
        self.query_one("#update-secret", Button).disabled = not has_secret
        self.query_one("#copy-secret", Button).disabled = not has_secret
        self.query_one("#collect-service-secrets", Button).disabled = (
            not has_manager or self._collecting_service_secrets
        )
        self.query_one("#activate-secret-manager", Button).disabled = (
            not self.can_activate_selected_manager()
        )

    def _count_available_managers(self) -> int:
        return sum(
            1 for manager in self._managers if manager.get("is_available") is True
        )

    def _count_service_managers(self) -> int:
        return sum(1 for manager in self._managers if manager.get("kind") == "service")

    def _format_secret_value(self, value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, sort_keys=True, default=str)
        return str(value)

    def _status_text(self, status: str) -> Text:
        if status == "available":
            return Text("available", style="bold green")
        if status == "unavailable":
            return Text("unavailable", style="bold red")
        return Text(status or "not checked", style="yellow")

    def _row_key_value(self, row_key: object) -> str:
        return str(getattr(row_key, "value", row_key))
