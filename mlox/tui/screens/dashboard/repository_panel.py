"""Project repository overview and read-only browser."""

from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Static

from mlox.application.use_cases.repositories import (
    clone_repository,
    describe_repositories,
    get_repository_deploy_keys,
    pull_repository,
    read_repository_file,
    refresh_repository,
)
from mlox.tui.widgets.file_browser import FileBrowser

from .model import SelectionInfo


class RepositoryPanel(Static):
    """Root-level repository service browser."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._rows: list[dict[str, Any]] = []
        self._row_ids: list[str] = []
        self._selected_repository_id = ""
        self._file_request_id = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="repository-content"):
            with Horizontal(id="repository-metrics"):
                yield Static(id="repository-metric-total", classes="repository-metric")
                yield Static(id="repository-metric-cloned", classes="repository-metric")
                yield Static(id="repository-metric-private", classes="repository-metric")
                yield Static(id="repository-metric-available", classes="repository-metric")
            with Horizontal(id="repository-actions"):
                yield Static("Project Repositories", id="repository-title")
                yield Button("Refresh", id="refresh-repository")
                yield Button("Clone", id="sync-repository")
                yield Button("Copy Deploy Key", id="copy-repository-deploy-keys")
            table = DataTable(id="repository-table")
            table.cursor_type = "row"
            table.add_columns(
                "Repository",
                "Bundle",
                "Server",
                "State",
                "Visibility",
                "Cloned",
                "Modified",
                "Message",
            )
            yield table
            yield FileBrowser(id="repository-file-browser")

    @property
    def table(self) -> DataTable:
        return self.query_one("#repository-table", DataTable)

    @property
    def browser(self) -> FileBrowser:
        return self.query_one("#repository-file-browser", FileBrowser)

    def on_mount(self) -> None:
        self._update_action_state()
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
        self._clear()
        self._set_action_loading(None)
        self.browser.show_message("Loading repositories...")

        def load_repositories() -> None:
            result = describe_repositories(infra)
            self.app.call_from_thread(self._show_repositories_result, result)

        self.app.run_worker(
            load_repositories,
            thread=True,
            exclusive=True,
            group="project-repositories",
        )

    @on(DataTable.RowSelected, "#repository-table")
    def handle_repository_selected(self, event: DataTable.RowSelected) -> None:
        repository_id = self._row_key(event)
        self._select_repository(repository_id, refresh=True)

    @on(Button.Pressed, "#refresh-repository")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self._refresh_selected_repository()

    @on(Button.Pressed, "#sync-repository")
    def handle_sync(self, _: Button.Pressed) -> None:
        row = self._selected_row()
        action = "pull" if bool(row and row.get("cloned")) else "clone"
        self._run_repository_action(action)

    @on(Button.Pressed, "#copy-repository-deploy-keys")
    def handle_copy_deploy_keys(self, _: Button.Pressed) -> None:
        repository_id = self._selected_repository_id
        if not repository_id:
            self.notify("Select a private repository with deploy keys.", severity="warning")
            return
        workspace = getattr(self.app, "workspace", None)
        result = get_repository_deploy_keys(workspace, repository_id)
        if not result.success:
            self.notify(result.message, severity="error")
            return
        keys = (result.data or {}).get("keys", {})
        if not keys:
            self.notify(
                "No deploy keys are available. Set up the repository service first.",
                severity="warning",
            )
            return
        payload = self._deploy_key_clipboard_payload(keys)
        self.app.copy_to_clipboard(payload)
        self.notify("Repository deploy key copied.")

    @on(FileBrowser.FileSelected, "#repository-file-browser")
    def handle_file_selected(self, event: FileBrowser.FileSelected) -> None:
        repository_id = self._selected_repository_id
        if not repository_id:
            return
        self._file_request_id += 1
        request_id = self._file_request_id
        path = event.path
        self.browser.show_message(f"Loading {event.entry.get('display_path', path)}...")
        workspace = getattr(self.app, "workspace", None)

        def load_file() -> None:
            result = read_repository_file(workspace, repository_id, path)
            self.app.call_from_thread(
                self._show_file_result,
                request_id,
                repository_id,
                path,
                result,
            )

        self.app.run_worker(
            load_file,
            thread=True,
            exclusive=True,
            group="repository-file-read",
        )

    def _show_repositories_result(self, result) -> None:
        if not self.selection or self.selection.type != "root":
            return
        if not result.success:
            self._rows = []
            self._populate_table()
            self._update_metrics()
            self.browser.show_message(result.message)
            self._update_action_state()
            return

        self._rows = list((result.data or {}).get("repositories", []))
        self._populate_table()
        self._update_metrics()
        if self._row_ids:
            self._select_repository(self._row_ids[0], refresh=True)
        else:
            self.browser.set_entries([], title="Repository Files")
        self._update_action_state()

    def _clear(self) -> None:
        self._rows = []
        self._row_ids = []
        self._selected_repository_id = ""
        self.table.clear(columns=False)
        self._update_metrics()
        self._update_action_state()

    def _populate_table(self) -> None:
        table = self.table
        table.clear(columns=False)
        self._row_ids = []
        if not self._rows:
            table.add_row("-", "-", "-", "-", "-", "-", "-", "No repositories found.")
            return

        for row in self._rows:
            repository_id = str(row.get("id") or "")
            if not repository_id:
                continue
            self._row_ids.append(repository_id)
            table.add_row(
                str(row.get("name", "-")),
                str(row.get("bundle", "-")),
                str(row.get("server", "-")),
                self._state_badge(str(row.get("state", "unknown"))),
                self._visibility_badge(bool(row.get("private"))),
                self._bool_badge(bool(row.get("cloned"))),
                str(row.get("modified") or "-"),
                str(row.get("message") or ""),
                key=repository_id,
            )
        if self._row_ids:
            index = max(0, self._row_ids.index(self._selected_repository_id)) if (
                self._selected_repository_id in self._row_ids
            ) else 0
            table.cursor_coordinate = (index, 0)

    def _select_repository(self, repository_id: str, *, refresh: bool) -> None:
        if repository_id not in self._row_ids:
            return
        self._selected_repository_id = repository_id
        self._update_action_state()
        row = self._selected_row()
        title = str(row.get("name", "Repository Files")) if row else "Repository Files"
        if row and row.get("private") and not row.get("deploy_keys_available"):
            self.browser.show_message(
                "Set up the repository service to generate deploy keys."
            )
        if refresh:
            self._refresh_selected_repository()
        else:
            self.browser.show_message("Refresh the repository to load files.")
        self.browser.tree.root.label = title

    def _refresh_selected_repository(self) -> None:
        repository_id = self._selected_repository_id
        if not repository_id:
            return
        self._set_action_loading("refresh")
        self.browser.show_loading("Checking repository...")
        workspace = getattr(self.app, "workspace", None)

        def refresh() -> None:
            result = refresh_repository(workspace, repository_id)
            self.app.call_from_thread(
                self._show_repository_refresh_result,
                repository_id,
                result,
            )

        self.app.run_worker(
            refresh,
            thread=True,
            exclusive=True,
            group="repository-refresh",
        )

    def _run_repository_action(self, action: str) -> None:
        repository_id = self._selected_repository_id
        if not repository_id:
            return
        self._set_action_loading(action)
        self.browser.show_loading(f"{action.capitalize()}ing repository...")
        workspace = getattr(self.app, "workspace", None)
        operation = clone_repository if action == "clone" else pull_repository

        def run() -> None:
            result = operation(workspace, repository_id)
            self.app.call_from_thread(
                self._show_repository_refresh_result,
                repository_id,
                result,
            )

        self.app.run_worker(
            run,
            thread=True,
            exclusive=True,
            group="repository-action",
        )

    def _show_repository_refresh_result(self, repository_id: str, result) -> None:
        self._set_action_loading(None)
        if repository_id != self._selected_repository_id:
            return
        if not result.success:
            self.browser.show_message(result.message)
            self.notify(result.message, severity="error")
            return
        payload = result.data or {}
        row = payload.get("repository")
        if isinstance(row, dict):
            self._upsert_row(row)
        tree = list(payload.get("tree", []))
        title = str(row.get("name", "Repository Files")) if isinstance(row, dict) else (
            "Repository Files"
        )
        self.browser.set_entries(tree, title=title)
        if isinstance(row, dict) and not row.get("cloned"):
            self.browser.show_message("Clone this repository to browse files.")
        self.notify(result.message)

    def _show_file_result(
        self,
        request_id: int,
        repository_id: str,
        path: str,
        result,
    ) -> None:
        if request_id != self._file_request_id:
            return
        if repository_id != self._selected_repository_id:
            return
        if not result.success:
            self.browser.show_message(result.message)
            return
        payload = result.data or {}
        self.browser.show_content(
            str(payload.get("content", "")),
            title=str(payload.get("name") or path),
        )

    def _upsert_row(self, row: dict[str, Any]) -> None:
        row_id = str(row.get("id") or "")
        for index, existing in enumerate(self._rows):
            if str(existing.get("id") or "") == row_id:
                self._rows[index] = row
                break
        else:
            self._rows.append(row)
        self._populate_table()
        self._update_metrics()
        self._update_action_state()

    def _set_action_loading(self, action: str | None) -> None:
        labels = {
            "refresh": "Refreshing...",
            "clone": "Cloning...",
            "pull": "Pulling...",
        }
        self.query_one("#refresh-repository", Button).label = (
            labels[action] if action == "refresh" else "Refresh"
        )
        sync_label = (
            labels[action]
            if action in {"clone", "pull"}
            else self._sync_action_label()
        )
        self.query_one("#sync-repository", Button).label = sync_label
        loading = action is not None
        for selector in (
            "#refresh-repository",
            "#sync-repository",
            "#copy-repository-deploy-keys",
        ):
            self.query_one(selector, Button).disabled = loading
        if not loading:
            self._update_action_state()

    def _update_action_state(self) -> None:
        if not self.is_mounted:
            return
        row = self._selected_row()
        has_row = bool(row)
        initialized = bool(row and row.get("state") != "un-initialized")
        private = bool(row and row.get("private"))
        has_deploy_keys = bool(row and row.get("deploy_keys_available"))
        self.query_one("#refresh-repository", Button).disabled = not has_row
        sync_button = self.query_one("#sync-repository", Button)
        sync_button.label = self._sync_action_label()
        sync_button.disabled = not (has_row and initialized)
        deploy_button = self.query_one("#copy-repository-deploy-keys", Button)
        deploy_button.display = private
        deploy_button.disabled = not has_deploy_keys

    def _sync_action_label(self) -> str:
        row = self._selected_row()
        return "Pull" if bool(row and row.get("cloned")) else "Clone"

    def _selected_row(self) -> dict[str, Any] | None:
        for row in self._rows:
            if str(row.get("id") or "") == self._selected_repository_id:
                return row
        return None

    def _deploy_key_clipboard_payload(self, keys: dict[str, Any]) -> str:
        public_key = str(keys.get("public") or "").strip()
        if public_key:
            return public_key
        return "\n\n".join(
            f"{label}:\n{str(value).strip()}" for label, value in keys.items()
        )

    def _update_metrics(self) -> None:
        total = len(self._rows)
        cloned = sum(1 for row in self._rows if row.get("cloned"))
        private = sum(1 for row in self._rows if row.get("private"))
        available = sum(
            1
            for row in self._rows
            if row.get("state") in {"running", "ready"} or row.get("cloned")
        )
        values = [
            ("#repository-metric-total", "Repositories", total, "cyan"),
            ("#repository-metric-cloned", "Cloned", cloned, "green"),
            ("#repository-metric-private", "Private", private, "yellow"),
            ("#repository-metric-available", "Available", available, "bright_green"),
        ]
        for selector, label, value, color in values:
            text = Text()
            text.append(f"{value}\n", style=f"bold {color}")
            text.append(label, style="dim")
            self.query_one(selector, Static).update(text)

    def _state_badge(self, state: str) -> Text:
        style = {
            "running": "bold white on dark_green",
            "ready": "bold white on dark_green",
            "un-initialized": "bold black on bright_yellow",
            "unknown": "bold white on grey23",
        }.get(state, "bold white on dark_blue")
        return Text(f" {state} ", style=style)

    def _visibility_badge(self, private: bool) -> Text:
        return Text(
            " private " if private else " public ",
            style="bold black on bright_yellow" if private else "bold white on dark_green",
        )

    def _bool_badge(self, value: bool) -> Text:
        return Text(
            " yes " if value else " no ",
            style="bold white on dark_green" if value else "bold white on grey23",
        )

    def _row_key(self, event: DataTable.RowSelected) -> str:
        row_key = getattr(event.row_key, "value", event.row_key)
        return str(row_key)
