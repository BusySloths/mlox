"""Overview panel displaying context-aware summaries."""

from __future__ import annotations

from typing import Optional

from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual.reactive import reactive
from textual.widgets import Static
from mlox.project.entries import parse_board

from mlox.application.use_cases.firewall import firewall_summary_for_bundle
from mlox.application.use_cases.project import summarize_infrastructure
from mlox.service import ServiceCapability

from .model import (
    SelectionInfo,
    WELCOME_TEXT,
    get_service_capabilities,
    get_server_backends,
    is_bundle_initialized,
)

PROJECT_SERVER_ROW_LIMIT = 8


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
        self.update(Panel(Text(WELCOME_TEXT, style="bold"), title="MLOX", border_style="#35635b"))

    def show_infrastructure_overview(self) -> None:
        workspace = getattr(self.app, "workspace", None)
        result = summarize_infrastructure(workspace)
        summary = result.data["summary"] if result.success and result.data else {}
        if not summary["has_data"]:
            self.update(
                Panel(
                    Text("No infrastructure available.\nAdd a server to start building this project.", style="bold #cbd5e1"),
                    title="Infrastructure Overview",
                    border_style="#35635b",
                    padding=(2, 3),
                )
            )
            return

        layout = Table.grid(expand=True, padding=(0, 1))
        layout.add_row(self._dashboard_heading(workspace, summary))
        layout.add_row(self._project_metric_panels(summary))
        layout.add_row(Columns(
            [self._system_checks(summary), self._knowledge_tasks(workspace)],
            expand=True,
            equal=True,
        ))
        layout.add_row(self._project_servers_table(summary["server_rows"]))

        self.update(
            Panel(
                layout,
                title="PROJECT DASHBOARD  ·  Infrastructure Overview",
                border_style="#35635b",
                padding=(1, 1),
            )
        )

    def _dashboard_heading(self, workspace, summary: dict) -> Text:
        totals = summary["totals"]
        return Text.assemble(
            (f"{getattr(workspace, 'name', 'Project')}  ", "bold #f8fafc"),
            ("·  ", "#35635b"),
            (f"{totals['bundles']} Bundles  ·  ", "#94a3b8"),
            (f"{getattr(workspace, 'active_secret_manager_name', 'No secret manager')}", "#94a3b8"),
        )

    def _project_metric_panels(self, summary: dict) -> Table:
        totals = summary["totals"]
        metrics = (
            ("Servers", str(totals["servers"]), "#69b7ff"),
            ("Services", str(totals["services"]), "#61d394"),
            ("Running", str(totals["running_services"]), "#8fe388"),
            ("Issues", str(totals["services_needing_attention"]), "#f4c95d" if totals["services_needing_attention"] else "#64748b"),
        )
        cards = []
        for label, value, color in metrics:
            cards.append(Panel(Text(value, style=f"bold {color}"), title=label, border_style=color, padding=(0, 1)))
        return Columns(cards, expand=True, equal=True)

    def _system_checks(self, summary: dict) -> Panel:
        totals = summary["totals"]
        rows = summary["server_rows"]
        running_servers = sum(str(row["state"]).casefold() == "running" for row in rows)
        servers = totals["servers"]
        firewall_servers = totals["firewall_capable_servers"]
        errors = totals["services_needing_attention"]
        checks = Table.grid(expand=True, padding=(0, 1))
        checks.add_column(width=2)
        checks.add_column()
        has_servers = servers > 0
        checks.add_row(
            self._check_mark(has_servers and running_servers == servers),
            Text(
                f"Server status  {running_servers}/{servers} running"
                if has_servers else "No servers registered"
            ),
        )
        checks.add_row(self._check_mark(errors == 0), Text("No reported service errors" if errors == 0 else f"Investigate {errors} service error(s)"))
        firewall_state = (
            f"Firewall capability  {firewall_servers}/{servers} servers; "
            "check active policy in Security"
        )
        checks.add_row(self._check_mark(has_servers and firewall_servers == servers), Text(firewall_state))
        resources = []
        if summary["cpu_available"]:
            resources.append(f"{totals['cpu']:g} CPU cores")
        if summary["ram_available"]:
            resources.append(f"{totals['ram']:.1f} GiB RAM")
        resource_text = (
            f"Resources reported  {totals['cpu']:g} CPU Cores · {totals['ram']:.1f} RAM (GiB)"
            if summary["cpu_available"] and summary["ram_available"]
            else "Resources reported  " + (" · ".join(resources) if resources else "not reported")
        )
        checks.add_row("·", Text(resource_text, style="dim"))
        return Panel(checks, title="SYSTEM CHECKS", border_style="#35635b", padding=(0, 1))

    def _check_mark(self, passed: bool) -> Text:
        return Text("✓" if passed else "!", style="bold #61d394" if passed else "bold #f4c95d")

    def _knowledge_tasks(self, workspace) -> Panel:
        rows = Table.grid(expand=True, padding=(0, 1))
        rows.add_column(width=2)
        rows.add_column()
        entries = []
        list_entries = getattr(workspace, "list_entries", None)
        if callable(list_entries):
            try:
                entries = list(list_entries())
            except Exception:
                entries = []
        tasks: list[tuple[str, str]] = []
        for entry in entries:
            if getattr(entry, "kind", "") not in {"todo", "board"}:
                continue
            for column in parse_board(str(getattr(entry, "body_md", "") or "")):
                for item in column.items:
                    if item.text.strip() and not item.checked:
                        tasks.append((str(getattr(entry, "title", "Task")), item.text.strip()))
        if tasks:
            for title, task in tasks[:5]:
                rows.add_row(Text("○", style="#f4c95d"), Text.assemble((task, "#cbd5e1"), (f"  · {title}", "dim")))
            if len(tasks) > 5:
                rows.add_row("·", Text(f"and {len(tasks) - 5} more open task(s)", style="dim"))
        else:
            rows.add_row(Text("✓", style="#61d394"), Text("No open tasks in Knowledge", style="#cbd5e1"))
            rows.add_row("·", Text("Add project follow-up in Operations → Knowledge", style="dim"))
        return Panel(rows, title=f"KNOWLEDGE  ·  {len(tasks)} OPEN", border_style="#35635b", padding=(0, 1))

    def _project_servers_table(self, server_rows: list[dict]) -> Table:
        table = Table(
            title="Server inventory",
            show_header=True,
            header_style="bold",
            expand=True,
        )
        table.add_column("Bundle / Server", style="#69b7ff")
        table.add_column("Backend")
        table.add_column("Server", width=13)
        table.add_column("Service states")

        if not server_rows:
            table.add_row("-", "-", "-", "-")
            return table

        for row in server_rows[:PROJECT_SERVER_ROW_LIMIT]:
            table.add_row(*self._project_server_cells(row))
        self._add_more_row(
            table,
            total=len(server_rows),
            shown=min(len(server_rows), PROJECT_SERVER_ROW_LIMIT),
            columns=4,
        )
        return table

    def _project_server_cells(self, row: dict) -> tuple:
        counts = row["service_states"]
        return (
            f"{row['bundle']}  ·  {row['server']}",
            row["backend"],
            self._state_badge(str(row["state"])),
            Text.assemble(
                (f"{counts.get('running', 0)} Running", "#61d394"),
                (f"   {counts.get('error', 0)} Errors", "#f4c95d" if counts.get("error", 0) else "dim"),
                (f"   {counts.get('un-initialized', 0)} Uninitialized", "dim"),
                (f"   {counts.get('other', 0)} Other", "dim"),
            ),
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
                self._firewall_summary_text(),
            )
        if is_bundle_initialized(bundle) and not services:
            details.add_row(
                "Services",
                (
                    "No services installed yet. Use Add Service in Bundle Actions "
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
        table.add_row(
            "Capabilities",
            self._capability_badges(get_service_capabilities(service)),
        )
        table.add_row("Version", str(getattr(service, "version", "-")))
        server_ip = getattr(getattr(bundle, "server", None), "ip", "unknown")
        table.add_row("Server", server_ip)
        table.add_row("Target Path", getattr(service, "target_path", "-"))
        template_id = getattr(service, "service_config_id", "-")
        table.add_row("Template", template_id)
        table.add_row("UUID", str(getattr(service, "uuid", "-")))
        capabilities = set(get_service_capabilities(service))
        if ServiceCapability.SECRET_MANAGER_BINDING.value in capabilities:
            table.add_row(
                "Secret Manager",
                self._runtime_provider_summary(
                    service,
                    getattr(service, "secret_manager_uuid", None),
                    include_credential=True,
                ),
            )
        if ServiceCapability.TELEMETRY_BINDING.value in capabilities:
            table.add_row(
                "Telemetry",
                self._runtime_provider_summary(
                    service,
                    getattr(service, "telemetry_uuid", None),
                ),
            )
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

    def _runtime_provider_summary(
        self,
        service: object,
        provider_uuid: str | None,
        *,
        include_credential: bool = False,
    ) -> str:
        provider_uuid = str(provider_uuid or "")
        if not provider_uuid:
            return "Not connected"

        lookup = getattr(service, "_service_lookup", None)
        get_service = getattr(lookup, "get_service_by_uuid", None)
        provider = get_service(provider_uuid) if callable(get_service) else None
        if provider is None:
            return f"UUID: {provider_uuid}\nProvider unavailable"

        lines = [
            f"Name: {getattr(provider, 'name', '-')}",
            f"UUID: {provider_uuid}",
        ]
        get_bundle = getattr(lookup, "get_bundle_by_service", None)
        provider_bundle = get_bundle(provider) if callable(get_bundle) else None
        provider_server = getattr(provider_bundle, "server", None)
        lines.append(f"Server: {getattr(provider_server, 'ip', '-')}")

        if include_credential:
            get_label = getattr(provider, "get_secret_manager_binding_label", None)
            binding_id = str(getattr(service, "uuid", "") or "")
            credential = get_label(binding_id) if callable(get_label) else None
            if credential:
                lines.append(f"Credential: {credential}")
        return "\n".join(lines)

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

    def _firewall_summary_text(self) -> Text:
        text = Text()
        text.append("Supported", style="bold white on dark_green")
        text.append("  Open the project Firewall tab for live status.", style="dim")
        return text
