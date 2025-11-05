"""History panel listing recent actions."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import DataTable, Static
from textual.containers import Container

from .model import SelectionInfo


class HistoryPanel(Container):
    """Display execution history for the selected server or service."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        table = DataTable(id="history-table")
        table.add_columns("Timestamp", "Action", "Status", "Details")
        yield table
        yield Static("", id="history-status")

    @property
    def table(self) -> DataTable:
        return self.query_one(DataTable)

    @property
    def status(self) -> Static:
        return self.query_one("#history-status", Static)

    def on_mount(self) -> None:
        self.status.update(
            "Select a server or service to view the latest history entries."
        )

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        self.table.clear(columns=False)
        if not selection or selection.type in {"root", "empty"}:
            self.status.update(
                "Select a server or service to view the latest history entries."
            )
            return
        entries = []
        label = "selection"

        if selection.type == "service" and selection.service:
            history = getattr(getattr(selection.service, "exec", None), "history", [])
            entries = self._prepare_entries(
                history, getattr(selection.service, "name", "service")
            )
            label = getattr(selection.service, "name", "service")
        else:
            history = getattr(getattr(selection.server, "exec", None), "history", [])
            entries = self._prepare_entries(
                history, getattr(selection.server, "ip", "server")
            )

        if not entries:
            self.status.update("No history available yet.")
            return

        for entry in entries:
            timestamp = entry["timestamp"]
            action = entry["action"]
            status = entry["status"]
            details = entry["details"]
            self.table.add_row(timestamp, action, status, details)

        self.status.update(f"Showing {len(entries)} most recent entries for {label}.")

    def _prepare_entries(
        self, history: Iterable[dict[str, Any]], source: str
    ) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        if not history:
            return entries
        for item in history:
            if not isinstance(item, dict):
                continue
            timestamp = str(item.get("timestamp", ""))
            action = str(item.get("action", ""))
            status = str(item.get("status", ""))
            details = self._format_history_details(item)
            entries.append(
                {
                    "timestamp": timestamp,
                    "action": f"{action} [{source}]" if source else action,
                    "status": status,
                    "details": details,
                }
            )
        entries.sort(key=lambda entry: entry["timestamp"], reverse=True)
        return entries[:25]

    def _format_history_details(self, entry: dict[str, Any]) -> str:
        parts: list[str] = []
        for key in ("command", "output", "error"):
            value = entry.get(key)
            if not value:
                continue
            text = str(value)
            if key == "output" and len(text) > 120:
                text = text[:117] + "…"
            parts.append(f"{key}: {text}")
        metadata = entry.get("metadata")
        if isinstance(metadata, dict) and metadata:
            meta_text = ", ".join(f"{k}={v}" for k, v in metadata.items())
            parts.append(f"meta[{meta_text}]")
        return " | ".join(parts) if parts else ""
