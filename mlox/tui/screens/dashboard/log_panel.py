"""Service log viewer panel."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Input, Select, Static

try:
    from textual.widgets import Log as LogWidget
except ImportError:  # pragma: no cover - fallback for older textual releases
    from textual.widgets import TextLog as LogWidget  # type: ignore

from .model import SelectionInfo


class LogPanel(Container):
    """Service log viewer."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        with Horizontal(id="log-controls"):
            yield Select(options=[], prompt="Compose label", id="log-label")
            yield Input(placeholder="Lines", id="log-tail", value="200")
            yield Button("Fetch", id="log-fetch")
        yield LogWidget(id="log-output", highlight=True)
        yield Static("", id="log-status")

    @property
    def label_input(self) -> Select:
        return self.query_one("#log-label", Select)

    @property
    def tail_input(self) -> Input:
        return self.query_one("#log-tail", Input)

    @property
    def log_output(self) -> LogWidget:
        return self.query_one(LogWidget)

    @property
    def status(self) -> Static:
        return self.query_one("#log-status", Static)

    def on_mount(self) -> None:
        self.status.update(
            "Select a service to fetch logs. Logs are retrieved on demand."
        )

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if selection and selection.type == "service" and selection.service:
            labels = list(
                getattr(selection.service, "compose_service_names", {}).keys()
            )
            if labels:
                options = [(label, label) for label in labels]
                self.label_input.set_options(options)
                self.label_input.value = labels[0]
                if not self._show_cached_logs(selection, labels[0]):
                    self.log_output.clear()
                    self.status.update("Ready to fetch logs for the selected service.")
            else:
                self.label_input.set_options([])
                self.label_input.clear()
                self.status.update("Selected service does not expose compose labels.")
        else:
            self.label_input.set_options([])
            self.label_input.clear()
            self.status.update(
                "Select a service to fetch logs. Logs are retrieved on demand."
            )
            self.log_output.clear()

    @on(Button.Pressed, "#log-fetch")
    def handle_fetch(self, _: Button.Pressed) -> None:  # pragma: no cover - UI callback
        selection = self.selection
        if not selection or selection.type != "service" or not selection.service:
            self.status.update("Please select a service to fetch logs.")
            return
        bundle = selection.bundle
        server = getattr(bundle, "server", None) if bundle else None
        if not bundle or not server:
            self.status.update("Associated server information is missing.")
            return
        raw_label = self.label_input.value
        label = raw_label.strip() if isinstance(raw_label, str) else ""
        labels = list(getattr(selection.service, "compose_service_names", {}).keys())
        if not label:
            if labels:
                label = labels[0]
            else:
                self.status.update("No compose labels available for this service.")
                return
        try:
            tail = int(self.tail_input.value.strip() or "200")
        except ValueError:
            self.status.update("Lines must be a number.")
            return

        service = selection.service
        self.status.update(f"Fetching logs for '{label}'…")

        def fetch_logs() -> None:
            try:
                with server.get_server_connection() as conn:
                    logs = service.compose_service_log_tail(conn, label=label, tail=tail)
            except Exception as exc:  # pragma: no cover - network/IO heavy
                self.app.call_from_thread(
                    self._show_logs, "", f"Failed to fetch logs: {exc}"
                )
                return
            self.app.call_from_thread(self._show_logs, logs, None)

        self.app.run_worker(fetch_logs, thread=True, exclusive=True, group="log-fetch")

    def _show_logs(self, logs: str, error: str | None) -> None:
        self.log_output.clear()
        if error:
            self.status.update(error)
            return
        for line in logs.splitlines() or [""]:
            self.log_output.write_line(line)
        self.status.update("Logs updated.")

    def _show_cached_logs(self, selection: SelectionInfo, label: str) -> bool:
        service = selection.service
        if not service:
            return False
        compose_map = getattr(service, "compose_service_names", {}) or {}
        container = compose_map.get(label)
        if not container:
            return False
        executor = getattr(service, "exec", None)
        if not executor:
            return False
        history = getattr(executor, "history", [])
        records = history if isinstance(history, list) else list(history)
        for entry in reversed(records):
            if not isinstance(entry, dict):
                continue
            if entry.get("action") != "docker_service_log_tails":
                continue
            metadata = entry.get("metadata") or {}
            if metadata.get("service_name") != container:
                continue
            logs = str(entry.get("output", ""))
            self.log_output.clear()
            for line in logs.splitlines() or [""]:
                self.log_output.write_line(line)
            timestamp = entry.get("timestamp")
            suffix = f" from {timestamp}" if timestamp else ""
            self.status.update(f"Showing cached logs{suffix}. Use Fetch to refresh.")
            return True
        return False
