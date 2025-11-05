"""Overview panel displaying context-aware summaries."""

from __future__ import annotations

from typing import Optional

from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual.reactive import reactive
from textual.widgets import Static
from textual.renderables.digits import Digits as DigitsRenderable

from mlox.session import MloxSession

from .model import (
    SelectionInfo,
    WELCOME_TEXT,
    summarize_infrastructure,
)


class OverviewPanel(Static):
    """Overview of the currently selected node."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def on_mount(self) -> None:
        self.show_default()

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not selection or selection.type == "empty":
            self.show_default()
            return
        if selection.type == "root":
            self.show_infrastructure_overview()
            return
        if selection.type == "service" and selection.service and selection.bundle:
            self.show_service(selection)
            return
        if selection.type == "server" and selection.server:
            self.show_server(selection)
            return
        if selection.type == "bundle" and selection.bundle:
            self.show_bundle(selection)
            return
        self.show_default()

    def show_default(self) -> None:
        self.update(
            Panel(
                Text(WELCOME_TEXT, style="bold"), title="Overview", border_style="green"
            )
        )

    def show_infrastructure_overview(self) -> None:
        session: Optional[MloxSession] = getattr(self.app, "session", None)
        summary = summarize_infrastructure(session)
        if not summary["has_data"]:
            self.update(
                Panel(
                    Text("No infrastructure available."),
                    title="Infrastructure Overview",
                    border_style="green",
                )
            )
            return

        totals = summary["totals"]
        metrics: list[tuple[str, str]] = [
            ("Bundles", str(totals["bundles"])),
            ("Servers", str(totals["servers"])),
            ("Services", str(totals["services"])),
            (
                "CPU Cores",
                f"{totals['cpu']:g}" if summary["cpu_available"] else "--",
            ),
            (
                "RAM (GiB)",
                f"{totals['ram']:.1f}" if summary["ram_available"] else "--",
            ),
        ]

        metric_panels = [
            Panel(
                DigitsRenderable(value),
                title=label,
                border_style="green",
                padding=(0, 1),
            )
            for label, value in metrics
        ]
        metrics_row = Columns(metric_panels, expand=True, equal=True)

        servers_table = Table(
            title="Servers", show_header=True, header_style="bold", expand=True
        )
        servers_table.add_column("IP", style="cyan")
        servers_table.add_column("State")
        servers_table.add_column("# Services", justify="right")
        if summary["server_rows"]:
            for row in summary["server_rows"]:
                servers_table.add_row(row[0], row[1], str(row[2]))
        else:
            servers_table.add_row("-", "-", "-")

        services_table = Table(
            title="Services", show_header=True, header_style="bold", expand=True
        )
        services_table.add_column("Name", style="cyan")
        services_table.add_column("Template")
        services_table.add_column("Server")
        services_table.add_column("State")
        if summary["service_rows"]:
            for row in summary["service_rows"]:
                services_table.add_row(row[0], row[1], row[2], row[3])
        else:
            services_table.add_row("-", "-", "-", "-")

        layout = Table.grid(expand=True, padding=(0, 1))
        layout.add_row(metrics_row)
        layout.add_row(servers_table)
        layout.add_row(services_table)

        self.update(
            Panel(
                layout,
                title="Infrastructure Overview",
                border_style="green",
            )
        )

    def show_bundle(self, selection: SelectionInfo) -> None:
        bundle = selection.bundle
        server = selection.server or getattr(bundle, "server", None)
        services = getattr(bundle, "services", []) or []
        service_names = ", ".join(getattr(svc, "name", "-") for svc in services) or "-"
        tags = ", ".join(getattr(bundle, "tags", []) or ["-"])
        table = Table.grid(expand=True)
        table.add_column(justify="right", style="cyan", ratio=1)
        table.add_column(justify="left", ratio=3)
        table.add_row("Bundle", str(getattr(bundle, "name", "-")))
        table.add_row("Tags", tags)
        table.add_row("Server IP", str(getattr(server, "ip", "unknown")))
        table.add_row("Server State", str(getattr(server, "state", "unknown")))
        table.add_row("Services", str(len(services)))
        table.add_row("Service Names", service_names)
        self.update(
            Panel(
                table,
                title=f"Bundle: {getattr(bundle, 'name', '-')}",
                border_style="green",
            )
        )

    def show_server(self, selection: SelectionInfo) -> None:
        server = selection.server
        table = Table.grid(expand=True)
        table.add_column(justify="right", style="cyan", ratio=1)
        table.add_column(justify="left", ratio=3)
        table.add_row("IP", str(getattr(server, "ip", "unknown")))
        table.add_row("State", str(getattr(server, "state", "unknown")))
        backend = ", ".join(getattr(server, "backend", []) or ["unknown"])
        table.add_row("Backend", backend)
        discovered = getattr(server, "discovered", None)
        table.add_row("Discovered", str(discovered) if discovered else "-")
        port = getattr(server, "port", "-")
        table.add_row("Port", str(port))
        service_config = getattr(server, "service_config_id", "-")
        table.add_row("Template", str(service_config))
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
        template_id = getattr(service, "service_config_id", "-")
        table.add_row("Template", template_id)
        compose_labels = ", ".join(
            getattr(service, "compose_service_names", {}).keys()
        ) or "-"
        table.add_row("Compose Labels", compose_labels)
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
