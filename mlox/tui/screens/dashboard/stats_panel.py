"""Statistics panel displaying metrics for selections."""

from __future__ import annotations

from typing import Dict, Optional

from rich.panel import Panel
from rich.table import Table

from textual.reactive import reactive
from textual.widgets import Static

from mlox.session import MloxSession

from .model import SelectionInfo, summarize_infrastructure


class StatsPanel(Static):
    """Display resource statistics for the selection."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def on_mount(self) -> None:
        self.show_placeholder()

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not selection or selection.type == "empty":
            self.show_placeholder()
            return
        if selection.type == "root":
            self.show_global_stats()
            return
        if selection.type == "server" and selection.server:
            self.show_server_stats(selection)
            return
        if selection.type == "bundle" and selection.bundle:
            self.show_bundle_stats(selection)
            return
        if selection.type == "service" and selection.service:
            self.show_service_stats(selection)
            return
        self.show_placeholder()

    def show_placeholder(self) -> None:
        self.update(Panel("Select a node to view stats.", title="Stats"))

    def show_server_stats(self, selection: SelectionInfo) -> None:
        server = selection.server
        table = Table(title="Server Resources", show_header=True, header_style="bold")
        table.add_column("Metric", justify="left", style="cyan")
        table.add_column("Value", justify="left")
        backend = ", ".join(getattr(server, "backend", []) or ["-"])
        table.add_row("Backend", backend)
        template_id = getattr(server, "service_config_id", "-")
        table.add_row("Template", str(template_id))
        info: Dict[str, object] = {}
        try:
            info = server.get_server_info()
        except Exception as exc:  # pragma: no cover - defensive UI code
            self.update(
                Panel(
                    f"Failed to load server info: {exc}",
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
        template_id = getattr(service, "service_config_id", "-")
        table.add_row("Template", template_id)
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

    def show_bundle_stats(self, selection: SelectionInfo) -> None:
        bundle = selection.bundle
        server = selection.server or getattr(bundle, "server", None)
        services = getattr(bundle, "services", []) or []
        table = Table(
            title="Bundle Summary", show_header=True, header_style="bold"
        )
        table.add_column("Metric", justify="left", style="cyan")
        table.add_column("Value", justify="left")
        table.add_row("Bundle", str(getattr(bundle, "name", "-")))
        table.add_row("Server IP", str(getattr(server, "ip", "unknown")))
        table.add_row("Server State", str(getattr(server, "state", "unknown")))
        tags = ", ".join(getattr(bundle, "tags", []) or ["-"])
        table.add_row("Tags", tags)
        table.add_row("Services", str(len(services)))
        if services:
            state_counts: Dict[str, int] = {}
            for svc in services:
                state = getattr(svc, "state", "unknown")
                state_counts[state] = state_counts.get(state, 0) + 1
            formatted_states = ", ".join(
                f"{state}: {count}" for state, count in state_counts.items()
            )
            table.add_row("Service States", formatted_states)
        self.update(Panel(table, title="Stats", border_style="green"))

    def show_global_stats(self) -> None:
        session: Optional[MloxSession] = getattr(self.app, "session", None)
        summary = summarize_infrastructure(session)
        if not summary["has_data"]:
            self.update(Panel("No infrastructure available.", title="Stats"))
            return
        totals = summary["totals"]
        table = Table(
            title="Infrastructure Totals", show_header=True, header_style="bold"
        )
        table.add_column("Metric", justify="left", style="cyan")
        table.add_column("Value", justify="left")
        table.add_row("Bundles", str(totals["bundles"]))
        table.add_row("Servers", str(totals["servers"]))
        table.add_row("Services", str(totals["services"]))
        if summary["cpu_available"]:
            table.add_row("CPU Cores", f"{totals['cpu']:g}")
        else:
            table.add_row("CPU Cores", "-")
        if summary["ram_available"]:
            table.add_row("RAM (GiB)", f"{totals['ram']:.1f}")
        else:
            table.add_row("RAM (GiB)", "-")
        self.update(Panel(table, title="Stats", border_style="green"))
