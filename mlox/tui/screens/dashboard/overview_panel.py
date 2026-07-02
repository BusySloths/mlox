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

from mlox.application.use_cases.firewall import firewall_summary_for_bundle
from mlox.application.use_cases.project import summarize_infrastructure

from .model import (
    SelectionInfo,
    WELCOME_TEXT,
    get_server_backends,
    is_bundle_initialized,
)

PROJECT_SERVER_ROW_LIMIT = 40


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
        workspace = getattr(self.app, "workspace", None)
        result = summarize_infrastructure(workspace)
        summary = result.data["summary"] if result.success and result.data else {}
        if not summary["has_data"]:
            self.update(
                Panel(
                    Text("No infrastructure available."),
                    title="Infrastructure Overview",
                    border_style="green",
                )
            )
            return

        layout = Table.grid(expand=True, padding=(0, 1))
        layout.add_row(self._project_metric_panels(summary))
        layout.add_row(self._project_servers_table(summary["server_rows"]))

        self.update(
            Panel(
                layout,
                title="Infrastructure Overview",
                border_style="green",
            )
        )

    def _project_metric_panels(self, summary: dict) -> Columns:
        totals = summary["totals"]
        metrics: list[tuple[str, str]] = [
            ("Bundles", str(totals["bundles"])),
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
        return Columns(
            [
                Panel(
                    DigitsRenderable(value),
                    title=label,
                    border_style="green",
                    padding=(0, 1),
                )
                for label, value in metrics
            ],
            expand=True,
            equal=True,
        )

    def _project_servers_table(self, server_rows: list[dict]) -> Table:
        table = Table(
            title="Servers",
            show_header=True,
            header_style="bold",
            expand=True,
        )
        table.add_column("Bundle", style="cyan")
        table.add_column("Server", style="cyan")
        table.add_column("Backend")
        table.add_column("State")
        table.add_column("Services", justify="right")
        table.add_column("Uninitialized", justify="right")
        table.add_column("Running", justify="right")
        table.add_column("Error", justify="right")
        table.add_column("Other", justify="right")

        if not server_rows:
            table.add_row("-", "-", "-", "-", "-", "-", "-", "-", "-")
            return table

        for row in server_rows[:PROJECT_SERVER_ROW_LIMIT]:
            table.add_row(*self._project_server_cells(row))
        self._add_more_row(
            table,
            total=len(server_rows),
            shown=min(len(server_rows), PROJECT_SERVER_ROW_LIMIT),
            columns=9,
        )
        return table

    def _project_server_cells(self, row: dict) -> tuple:
        counts = row["service_states"]
        return (
            row["bundle"],
            row["server"],
            row["backend"],
            self._state_badge(str(row["state"])),
            str(row["services"]),
            self._service_count_badge(counts, "un-initialized"),
            self._service_count_badge(counts, "running"),
            self._service_count_badge(counts, "error"),
            self._service_count_badge(counts, "other"),
        )

    def _add_more_row(
        self,
        table: Table,
        *,
        total: int,
        shown: int,
        columns: int,
    ) -> None:
        remaining = total - shown
        if remaining <= 0:
            return
        cells = [f"... {remaining} more not shown"]
        cells.extend([""] * (columns - 1))
        table.add_row(*cells, style="dim")

    def show_bundle(self, selection: SelectionInfo) -> None:
        bundle = selection.bundle
        server = selection.server or getattr(bundle, "server", None)
        services = getattr(bundle, "services", []) or []
        backends = ", ".join(get_server_backends(server)) or "unknown"
        details = Table.grid(expand=True)
        details.add_column(justify="right", style="cyan", no_wrap=True)
        details.add_column(justify="left", ratio=3)
        details.add_row("Tags", self._tag_badges(getattr(bundle, "tags", []) or []))
        details.add_row("Server", str(getattr(server, "ip", "unknown")))
        details.add_row("State", str(getattr(server, "state", "unknown")))
        details.add_row("Backend", backends)
        firewall = firewall_summary_for_bundle(bundle)
        if firewall["capable"]:
            details.add_row(
                "Firewall",
                self._firewall_summary_text(firewall["recommended_ports"]),
            )
        if is_bundle_initialized(bundle) and not services:
            details.add_row(
                "Services",
                (
                    "No services installed yet. Use the Service Templates tab "
                    "to add backend-specific services."
                ),
            )

        self.update(
            Panel(
                details,
                title=f"Bundle: {getattr(bundle, 'name', '-')}",
                border_style="green",
                padding=(1, 2),
            )
        )

    def show_server(self, selection: SelectionInfo) -> None:
        server = selection.server
        table = Table.grid(expand=True)
        table.add_column(justify="right", style="cyan", ratio=1)
        table.add_column(justify="left", ratio=3)
        table.add_row("IP", str(getattr(server, "ip", "unknown")))
        table.add_row("State", str(getattr(server, "state", "unknown")))
        backend = ", ".join(get_server_backends(server)) or "unknown"
        table.add_row("Backend", backend)
        table.add_row(
            "Capabilities",
            self._capability_badges(getattr(server, "capabilities", set()) or []),
        )
        discovered = getattr(server, "discovered", None)
        table.add_row("Discovered", str(discovered) if discovered else "-")
        port = getattr(server, "port", "-")
        table.add_row("Port", str(port))
        service_config = getattr(server, "service_config_id", "-")
        table.add_row("Template", str(service_config))
        for label, value in self._server_resource_rows(server):
            table.add_row(label, value)
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
        table.add_row("Version", str(getattr(service, "version", "-")))
        server_ip = getattr(getattr(bundle, "server", None), "ip", "unknown")
        table.add_row("Server", server_ip)
        table.add_row("Target Path", getattr(service, "target_path", "-"))
        template_id = getattr(service, "service_config_id", "-")
        table.add_row("Template", template_id)
        table.add_row("UUID", str(getattr(service, "uuid", "-")))
        table.add_row(
            "Ports", self._format_ports(getattr(service, "service_ports", None))
        )
        compose_labels = (
            ", ".join(getattr(service, "compose_service_names", {}).keys()) or "-"
        )
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

    def _server_resource_rows(self, server: object) -> list[tuple[str, str]]:
        get_info = getattr(server, "get_server_info", None)
        if not callable(get_info):
            return []

        try:
            info = get_info()
        except Exception as exc:  # pragma: no cover - defensive UI code
            return [("Resource Info", f"Failed to load: {exc}")]
        if not isinstance(info, dict):
            return []

        rows = []
        for key in ["cpu_count", "ram_gb", "storage_gb", "os", "kernel_version"]:
            value = info.get(key)
            if value is not None:
                rows.append((key.replace("_", " ").title(), str(value)))
        uptime = info.get("uptime")
        if uptime:
            rows.append(("Uptime", str(uptime)))
        return rows

    def _tag_badges(self, tags: list[object]) -> Text:
        if not tags:
            return Text("No tags", style="dim")

        palette = [
            "bold white on dark_green",
            "bold white on dark_blue",
            "bold black on bright_yellow",
            "bold white on dark_cyan",
            "bold black on bright_white",
        ]
        badges = Text()
        for index, tag in enumerate(tags):
            if index:
                badges.append("  ")
            badges.append(f" {str(tag)} ", style=palette[index % len(palette)])
        return badges

    def _capability_badges(self, capabilities: object) -> Text:
        names = set()
        for capability in capabilities:
            value = capability.value if hasattr(capability, "value") else capability
            name = str(value).strip().replace("-", "_")
            if name:
                names.add(name)
        if not names:
            return Text("None", style="dim")

        palette = [
            "bold white on dark_blue",
            "bold white on dark_green",
            "bold black on bright_yellow",
            "bold white on dark_cyan",
            "bold black on bright_white",
        ]
        badges = Text()
        for index, name in enumerate(sorted(names)):
            if index:
                badges.append("  ")
            label = name.replace("_", " ")
            badges.append(f" {label} ", style=palette[index % len(palette)])
        return badges

    def _state_badge(self, state: str) -> Text:
        label = state.replace("_", " ")
        style = {
            "running": "bold white on dark_green",
            "healthy": "bold white on dark_green",
            "pending": "bold black on bright_yellow",
            "starting": "bold black on bright_yellow",
            "failed": "bold white on dark_red",
            "error": "bold white on dark_red",
            "unhealthy": "bold white on dark_red",
            "degraded": "bold black on yellow",
            "stopped": "bold white on grey23",
            "unknown": "bold white on grey23",
        }.get(state, "bold white on dark_blue")
        return Text(f" {label} ", style=style)

    def _service_count_badge(self, counts: dict[str, int], group: str) -> Text:
        count = counts.get(group, 0)
        if count == 0:
            return Text("0", style="dim")
        style = {
            "un-initialized": "bold black on bright_yellow",
            "running": "bold white on dark_green",
            "error": "bold white on dark_red",
            "other": "bold white on dark_blue",
        }[group]
        return Text(str(count), style=style)

    def _format_ports(self, ports: object) -> str:
        if isinstance(ports, dict) and ports:
            return ", ".join(f"{key}:{value}" for key, value in ports.items())
        return "-"

    def _firewall_summary_text(self, recommended_ports: list[int]) -> Text:
        text = Text()
        text.append("Supported", style="bold white on dark_green")
        text.append("  Recommended ports: ")
        text.append(", ".join(str(port) for port in recommended_ports) or "none")
        text.append("  Open the project Firewall tab for live status.", style="dim")
        return text
