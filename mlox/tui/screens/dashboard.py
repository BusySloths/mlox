"""Dashboard screen providing infrastructure insights within the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Select,
    Static,
    TabPane,
    TabbedContent,
    Tree,
)

try:
    from textual.widgets import Log as LogWidget
except ImportError:  # pragma: no cover - fallback for older textual releases
    from textual.widgets import TextLog as LogWidget  # type: ignore

from mlox.config import load_all_server_configs, load_all_service_configs
from mlox.session import MloxSession

WELCOME_TEXT = """\
Accelerate your ML journey—deploy production-ready MLOps in minutes, not months.

MLOX helps individuals and small teams deploy, configure, and monitor full
MLOps stacks with minimal effort.
"""


@dataclass
class SelectionInfo:
    """Normalized information about the selected tree node."""

    type: str
    bundle: Any | None = None
    server: Any | None = None
    service: Any | None = None


class SelectionChanged(Message):
    """Message broadcast whenever the selection in the tree changes."""

    def __init__(self, selection: Optional[SelectionInfo]) -> None:
        super().__init__()
        self.selection = selection


class InfraTree(Tree[SelectionInfo]):
    """Tree showing the current infrastructure bundles, servers and services."""

    def __init__(self) -> None:
        super().__init__("Infrastructure", id="infra-tree")

    def on_mount(self) -> None:
        self.populate_tree()

    def populate_tree(self) -> None:
        """Populate the tree with bundles, servers and services."""

        self.clear()
        self.root.label = "Infrastructure"
        self.root.data = SelectionInfo(type="root")

        session: Optional[MloxSession] = getattr(self.app, "session", None)
        infra = getattr(session, "infra", None)
        if not infra or not infra.bundles:
            self.root.add(
                "No infrastructure available", data=SelectionInfo(type="empty")
            )
            self.root.expand()
            return

        for bundle in infra.bundles:
            bundle_node = self.root.add(
                f"Bundle: {bundle.name}",
                data=SelectionInfo(type="bundle", bundle=bundle, server=bundle.server),
            )
            bundle_node.expand()
            server = getattr(bundle, "server", None)
            server_label = (
                f"Server: {getattr(server, 'ip', 'unknown')}"
                if server
                else "Server: unknown"
            )
            bundle_node.add(
                server_label,
                data=SelectionInfo(type="server", bundle=bundle, server=server),
            )
            if not bundle.services:
                bundle_node.add("No services", data=SelectionInfo(type="empty"))
                continue
            for svc in bundle.services:
                bundle_node.add(
                    f"Service: {svc.name}",
                    data=SelectionInfo(
                        type="service", bundle=bundle, server=server, service=svc
                    ),
                )
        self.root.expand()

    def on_tree_node_selected(
        self, event: Tree.NodeSelected
    ) -> None:  # pragma: no cover - UI callback
        data = event.node.data
        selection = data if isinstance(data, SelectionInfo) else None
        self.post_message(SelectionChanged(selection))


class OverviewPanel(Static):
    """Overview of the currently selected node."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def on_mount(self) -> None:
        self.show_default()

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not selection or selection.type in {"root", "empty"}:
            self.show_default()
            return
        if selection.type == "service" and selection.service and selection.bundle:
            self.show_service(selection)
            return
        if (
            selection.type in {"server", "bundle"}
            and selection.server
            and selection.bundle
        ):
            self.show_server(selection)
            return
        self.show_default()

    def show_default(self) -> None:
        self.update(
            Panel(
                Text(WELCOME_TEXT, style="bold"), title="Overview", border_style="green"
            )
        )

    def show_server(self, selection: SelectionInfo) -> None:
        server = selection.server
        table = Table.grid(expand=True)
        table.add_column(justify="right", style="cyan", ratio=1)
        table.add_column(justify="left", ratio=3)
        table.add_row("Bundle", str(getattr(selection.bundle, "name", "-")))
        table.add_row("IP", str(getattr(server, "ip", "unknown")))
        table.add_row("State", str(getattr(server, "state", "unknown")))
        backend = ", ".join(getattr(server, "backend", []) or ["unknown"])
        table.add_row("Backend", backend)
        tags = ", ".join(getattr(selection.bundle, "tags", []) or ["-"])
        table.add_row("Tags", tags)
        discovered = getattr(server, "discovered", False)
        table.add_row("Discovered", "Yes" if discovered else "No")
        self.update(
            Panel(
                table,
                title=f"Server: {getattr(server, 'ip', 'unknown')}",
                border_style="green",
            )
        )

    def show_service(self, selection: SelectionInfo) -> None:
        service = selection.service
        bundle = selection.bundle
        table = Table.grid(expand=True)
        table.add_column(justify="right", style="cyan", ratio=1)
        table.add_column(justify="left", ratio=3)
        table.add_row("Bundle", str(getattr(bundle, "name", "-")))
        table.add_row("Service", getattr(service, "name", "-"))
        table.add_row("State", getattr(service, "state", "unknown"))
        server_ip = getattr(getattr(bundle, "server", None), "ip", "unknown")
        table.add_row("Server", server_ip)
        table.add_row("Target Path", getattr(service, "target_path", "-"))
        urls = getattr(service, "service_urls", None) or {}
        if urls:
            formatted_urls = "\n".join(f"{k}: {v}" for k, v in urls.items())
        else:
            formatted_urls = "-"
        table.add_row("URLs", formatted_urls)
        self.update(
            Panel(
                table,
                title=f"Service: {getattr(service, 'name', '-')}",
                border_style="green",
            )
        )


class StatsPanel(Static):
    """Display resource statistics for the selection."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def on_mount(self) -> None:
        self.update(Panel(Text("Select a node to view stats."), title="Stats"))

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not selection or selection.type in {"root", "empty"}:
            self.update(Panel(Text("Select a node to view stats."), title="Stats"))
            return
        if selection.type in {"server", "bundle"} and selection.server:
            self.show_server_stats(selection)
            return
        if selection.type == "service" and selection.service:
            self.show_service_stats(selection)
            return
        self.update(Panel(Text("Stats not available."), title="Stats"))

    def show_server_stats(self, selection: SelectionInfo) -> None:
        server = selection.server
        table = Table(title="Server Resources", show_header=True, header_style="bold")
        table.add_column("Metric", justify="left", style="cyan")
        table.add_column("Value", justify="left")
        info = {}
        try:
            info = server.get_server_info()
        except Exception as exc:  # pragma: no cover - defensive UI code
            self.update(
                Panel(
                    Text(f"Failed to load server info: {exc}"),
                    title="Stats",
                    border_style="red",
                )
            )
            return
        for key in ["cpu_count", "ram_gb", "storage_gb", "os", "kernel_version"]:
            value = info.get(key, "-") if isinstance(info, dict) else "-"
            table.add_row(key.replace("_", " ").title(), str(value))
        uptime = info.get("uptime") if isinstance(info, dict) else None
        if uptime:
            table.add_row("Uptime", str(uptime))
        bundle = selection.bundle
        if bundle and getattr(bundle, "services", None):
            table.add_row("Services", str(len(bundle.services)))
        self.update(Panel(table, title="Stats", border_style="green"))

    def show_service_stats(self, selection: SelectionInfo) -> None:
        service = selection.service
        bundle = selection.bundle
        table = Table(title="Service Details", show_header=True, header_style="bold")
        table.add_column("Metric", justify="left", style="cyan")
        table.add_column("Value", justify="left")
        table.add_row("Name", getattr(service, "name", "-"))
        table.add_row("State", getattr(service, "state", "unknown"))
        table.add_row("Version", str(getattr(service, "version", "-")))
        table.add_row("Bundle", str(getattr(bundle, "name", "-")))
        ports = getattr(service, "service_ports", None)
        if isinstance(ports, dict) and ports:
            formatted_ports = ", ".join(f"{k}:{v}" for k, v in ports.items())
        else:
            formatted_ports = "-"
        table.add_row("Ports", formatted_ports)
        table.add_row("UUID", getattr(service, "uuid", "-"))
        compose_labels = list(getattr(service, "compose_service_names", {}).keys())
        if compose_labels:
            table.add_row("Compose Labels", ", ".join(compose_labels))
        self.update(Panel(table, title="Stats", border_style="green"))


class HistoryPanel(Container):
    """Display execution history for the selected server or service."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        # yield Static("History", classes="section-title")
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


class LogPanel(Container):
    """Service log viewer."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def compose(self) -> ComposeResult:
        # yield Static("Logs", classes="section-title")
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
                    logs = service.compose_service_log_tail(
                        conn, label=label, tail=tail
                    )
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


class TemplatePanel(Static):
    """List available server and service templates."""

    def on_mount(self) -> None:
        self.update(self._build_panel())

    def _build_panel(self) -> Panel:
        server_table = Table(
            title="Server Templates", show_header=True, header_style="bold"
        )
        server_table.add_column("Name", style="cyan")
        server_table.add_column("Version")
        server_table.add_column("Maintainer")
        server_configs = load_all_server_configs()
        if server_configs:
            for cfg in server_configs:
                server_table.add_row(cfg.name, str(cfg.version), cfg.maintainer)
        else:
            server_table.add_row("-", "-", "-")

        service_table = Table(
            title="Service Templates", show_header=True, header_style="bold"
        )
        service_table.add_column("Name", style="cyan")
        service_table.add_column("Version")
        service_table.add_column("Maintainer")
        service_configs = load_all_service_configs()
        if service_configs:
            for cfg in service_configs:
                service_table.add_row(cfg.name, str(cfg.version), cfg.maintainer)
        else:
            service_table.add_row("-", "-", "-")

        outer = Table.grid(padding=1)
        outer.add_row(server_table)
        outer.add_row(service_table)
        return Panel(outer, title="Templates", border_style="green")


class DashboardScreen(Screen):
    """Main dashboard shown after a successful login."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, classes="app-header")
        with Container(id="main-area"):
            with Container(id="sidebar"):
                yield InfraTree()
            with Container(id="detail-panel"):
                with Container(id="upper-pane"):
                    with Horizontal(id="summary-pane"):
                        yield OverviewPanel(id="selection-overview")
                        yield StatsPanel(id="selection-stats")
                with Container(id="activity-container"):
                    with TabbedContent(id="activity-tabs"):
                        with TabPane("Logs", id="logs-tab"):
                            yield LogPanel(id="selection-logs")
                        with TabPane("History", id="history-tab"):
                            yield HistoryPanel(id="selection-history")
        yield Footer(classes="app-footer")

    def on_mount(self) -> None:
        tree = self.query_one(InfraTree)
        tree.populate_tree()

    def on_selection_changed(self, message: SelectionChanged) -> None:
        selection = message.selection
        overview = self.query_one(OverviewPanel)
        overview.selection = selection
        stats = self.query_one(StatsPanel)
        stats.selection = selection
        logs = self.query_one(LogPanel)
        logs.selection = selection
        history = self.query_one(HistoryPanel)
        history.selection = selection
