"""Inline runtime information panels for server and bundle selections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static

from mlox.application.use_cases.servers import get_backend_info, get_server_info

from .model import SelectionInfo


@dataclass(frozen=True)
class RuntimeInfoDisplay:
    """Rendered runtime information split between controls and content."""

    summary: str
    content: object


class ServerInfoPanel(Container):
    """Display and cache runtime server/backend information."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._cache: dict[tuple[str, int], Any] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="server-info-controls"):
            yield Button("Refresh", id="refresh-server-info", variant="primary")
            yield Static("", id="server-info-summary", markup=False)
        yield Static(
            "Select a server or bundle to load runtime information.",
            id="server-runtime-info",
            markup=False,
        )

    def on_mount(self) -> None:
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return

        self.display = selection is not None and selection.type in {"bundle", "server"}
        self._render_title(selection)
        if not self.display:
            return

        title = self.query_one("#refresh-server-info", Button)
        server = self._selected_server(selection)
        output = self.query_one("#server-runtime-info", Static)
        if not server:
            output.update(
                "Select a server or bundle to load runtime information."
            )
            self.query_one("#server-info-summary", Static).update("")
            title.disabled = True
            return

        title.disabled = False
        cached = self._cache.get(self._cache_key(selection, server))
        if cached is not None:
            self._show_runtime_display(cached)
            return

        self.query_one("#server-info-summary", Static).update("")
        output.update(self._empty_message(selection))

    @on(Button.Pressed, "#refresh-server-info")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.load_selected_info(refresh=True)

    def load_selected_info(self, *, refresh: bool = False) -> bool:
        """Show cached information or load it in the background."""

        selection = self.selection
        server = self._selected_server(selection)
        if not server:
            return False

        cache_key = self._cache_key(selection, server)
        cached = self._cache.get(cache_key)
        output = self.query_one("#server-runtime-info", Static)
        if cached is not None and not refresh:
            self._show_runtime_display(cached)
            return True

        self.query_one("#refresh-server-info", Button).disabled = True
        self.query_one("#server-info-summary", Static).update("")
        output.update(self._loading_message(selection))

        def load_info() -> None:
            try:
                result = self._load_info(selection, server)
                self.app.call_from_thread(
                    self._show_info_result,
                    selection,
                    server,
                    result,
                )
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                logger = getattr(self.app, "log", None)
                if hasattr(logger, "error"):
                    logger.error("Failed to load server information: %s", exc)
                try:
                    self.app.call_from_thread(
                        self._show_server_info_error,
                        selection,
                        server,
                        f"Failed to load runtime information: {exc}",
                    )
                except Exception:
                    pass

        self.app.run_worker(
            load_info,
            thread=True,
            exclusive=True,
            group="server-info",
        )
        return True

    def _show_info_result(self, selection: Optional[SelectionInfo], server: object, result) -> None:
        if selection != self.selection or server is not self._selected_server(self.selection):
            return

        self.query_one("#refresh-server-info", Button).disabled = False
        if not result.success:
            self.notify(result.message, severity="error")
            self.query_one("#server-info-summary", Static).update("")
            self.query_one("#server-runtime-info", Static).update("")
            return

        rendered = self._format_runtime_info(selection, result.data or {})
        self._cache[self._cache_key(selection, server)] = rendered
        self._show_runtime_display(rendered)

    def _show_server_info_error(
        self, selection: Optional[SelectionInfo], server: object, message: str
    ) -> None:
        if selection != self.selection or server is not self._selected_server(self.selection):
            return

        self.query_one("#refresh-server-info", Button).disabled = False
        self.query_one("#server-info-summary", Static).update("")
        self.query_one("#server-runtime-info", Static).update(message)
        self.notify(message, severity="error")

    def _show_runtime_display(self, rendered: object) -> None:
        if isinstance(rendered, RuntimeInfoDisplay):
            self.query_one("#server-info-summary", Static).update(rendered.summary)
            self.query_one("#server-runtime-info", Static).update(rendered.content)
            return

        self.query_one("#server-info-summary", Static).update("")
        self.query_one("#server-runtime-info", Static).update(rendered)

    def _selected_server(self, selection: Optional[SelectionInfo]) -> object | None:
        server = selection.server if selection else None
        if not server and selection:
            server = getattr(selection.bundle, "server", None)
        return server

    def _cache_key(self, selection: Optional[SelectionInfo], server: object) -> tuple[str, int]:
        mode = selection.type if selection else "server"
        return (mode, id(server))

    def _load_info(self, selection: Optional[SelectionInfo], server: object):
        if selection and selection.type == "bundle":
            return get_backend_info(server)
        return get_server_info(server)

    def _format_runtime_info(
        self, selection: Optional[SelectionInfo], data: dict
    ) -> object:
        sections: list[str] = []
        if selection and selection.type == "bundle":
            backend_info = data.get("backend_info") or {}
            docker_table = self._format_docker_backend(backend_info)
            if docker_table is not None:
                return docker_table
            kubernetes_table = self._format_kubernetes_backend(backend_info)
            if kubernetes_table is not None:
                return kubernetes_table
            sections.extend(self._format_mapping(backend_info))
        else:
            return self._format_server_info(data.get("server_info") or {})
        return "\n".join(sections)

    def _render_title(self, selection: Optional[SelectionInfo]) -> None:
        if selection and selection.type == "bundle":
            self.border_title = "Backend"
            return
        if selection and selection.type == "server":
            self.border_title = "Server Info"
            return
        self.border_title = "Runtime Info"

    def _format_docker_backend(self, backend_info: object) -> RuntimeInfoDisplay | None:
        if not isinstance(backend_info, dict):
            return None
        if not any(str(key).startswith("docker.") for key in backend_info):
            return None

        containers = backend_info.get("docker.containers")
        container_count = str(len(containers)) if isinstance(containers, list) else "-"
        summary = " | ".join(
            [
                f"Docker: {self._format_bool(backend_info.get('docker.is_running'))}",
                f"Enabled: {self._format_bool(backend_info.get('docker.is_enabled'))}",
                f"Client: {self._docker_version(backend_info.get('docker.version'), 'Client')}",
                f"Server: {self._docker_version(backend_info.get('docker.version'), 'Server')}",
                f"Containers: {container_count}",
            ]
        )
        if not isinstance(containers, list):
            return RuntimeInfoDisplay(summary=summary, content=str(containers or "-"))

        container_table = Table(
            title="Containers",
            show_header=True,
            header_style="bold",
            expand=True,
        )
        container_table.add_column("Name", style="cyan", no_wrap=True)
        container_table.add_column("Image", no_wrap=True, overflow="ellipsis")
        container_table.add_column("State", no_wrap=True)
        container_table.add_column("Status", no_wrap=True, overflow="ellipsis")
        container_table.add_column("Ports", no_wrap=True, overflow="ellipsis")

        if containers:
            for container in containers:
                if not isinstance(container, dict):
                    continue
                container_table.add_row(
                    self._short_value(container.get("Names")),
                    self._short_value(container.get("Image")),
                    self._short_value(container.get("State")),
                    self._short_value(container.get("Status")),
                    self._short_value(container.get("Ports")),
                )
        else:
            container_table.add_row("-", "-", "-", "-", "-")

        return RuntimeInfoDisplay(summary=summary, content=container_table)

    def _format_kubernetes_backend(
        self, backend_info: object
    ) -> RuntimeInfoDisplay | None:
        if not isinstance(backend_info, dict):
            return None
        if not any(str(key).startswith("k3s") for key in backend_info):
            return None

        nodes = backend_info.get("k3s.nodes")
        node_count = str(len(nodes)) if isinstance(nodes, list) else "-"
        summary = " | ".join(
            [
                f"Backend: {self._format_bool(backend_info.get('backend.is_running'))}",
                f"k3s: {self._format_bool(backend_info.get('k3s.is_running'))}",
                f"agent: {self._format_bool(backend_info.get('k3s-agent.is_running'))}",
                f"nodes: {node_count}",
            ]
        )
        if not isinstance(nodes, list):
            return RuntimeInfoDisplay(summary=summary, content="-")

        nodes_table = Table(
            title="Kubernetes Nodes",
            show_header=True,
            header_style="bold",
            expand=True,
        )
        nodes_table.add_column("Name", style="cyan", no_wrap=True)
        nodes_table.add_column("Status", no_wrap=True)
        nodes_table.add_column("Roles", no_wrap=True, overflow="ellipsis")
        nodes_table.add_column("Version", no_wrap=True)
        nodes_table.add_column("Internal IP", no_wrap=True)
        nodes_table.add_column("OS", overflow="ellipsis")
        nodes_table.add_column("Runtime", overflow="ellipsis")

        if nodes:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                nodes_table.add_row(
                    self._short_value(node.get("NAME")),
                    self._short_value(node.get("STATUS")),
                    self._short_value(node.get("ROLES")),
                    self._short_value(node.get("VERSION")),
                    self._short_value(node.get("INTERNAL-IP")),
                    self._short_value(node.get("OS-IMAGE")),
                    self._short_value(node.get("CONTAINER-RUNTIME")),
                )
        else:
            nodes_table.add_row("-", "-", "-", "-", "-", "-", "-")

        return RuntimeInfoDisplay(summary=summary, content=nodes_table)

    def _format_server_info(self, server_info: object) -> object:
        if not isinstance(server_info, dict) or not server_info:
            return "-"

        table = Table(
            title="System",
            show_header=True,
            header_style="bold",
            expand=True,
        )
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", overflow="fold")

        used_keys: set[str] = set()

        def add_row(key: str, label: str) -> None:
            value = server_info.get(key)
            if value in (None, ""):
                return
            used_keys.add(key)
            table.add_row(label, Text(str(value)))

        os_value = (
            server_info.get("pretty_name")
            or server_info.get("name")
            or server_info.get("id")
        )
        if os_value not in (None, ""):
            used_keys.update({"pretty_name", "name", "id"})

        add_row("host", "Host")
        if os_value not in (None, ""):
            table.add_row("OS", Text(str(os_value)))
        add_row("version_id", "Version")
        add_row("version_codename", "Codename")
        add_row("ubuntu_codename", "Ubuntu Codename")
        add_row("id_like", "ID Like")
        add_row("cpu_count", "CPU Cores")
        add_row("ram_gb", "RAM (GiB)")
        add_row("storage_gb", "Storage (GiB)")

        fallback_keys = [
            key
            for key in sorted(server_info, key=str)
            if key not in used_keys and not self._is_noisy_server_info_key(key)
        ]
        for key in fallback_keys[:8]:
            table.add_row(self._format_label(key), Text(str(server_info[key])))

        return table

    def _format_bool(self, value: object) -> str:
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value) if value is not None else "-"

    def _docker_version(self, version: object, section: str) -> str:
        if not isinstance(version, dict):
            return str(version) if version else "-"
        section_data = version.get(section)
        if isinstance(section_data, dict):
            return str(
                section_data.get("Version") or section_data.get("ApiVersion") or "-"
            )
        return "-"

    def _short_value(self, value: object, *, limit: int = 80) -> str:
        text = str(value) if value not in (None, "") else "-"
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _is_noisy_server_info_key(self, key: object) -> bool:
        text = str(key)
        return text.endswith("_url") or text in {"logo"}

    def _format_label(self, key: object) -> str:
        return str(key).replace("_", " ").title()

    def _empty_message(self, selection: Optional[SelectionInfo]) -> str:
        if selection and selection.type == "bundle":
            return "Press Refresh to load backend information."
        return "Press Refresh to load server information."

    def _loading_message(self, selection: Optional[SelectionInfo]) -> str:
        if selection and selection.type == "bundle":
            return "Loading backend information..."
        return "Loading server information..."

    def _format_mapping(self, values: object) -> list[str]:
        if not isinstance(values, dict) or not values:
            return ["-"]
        return [f"{key}: {values[key]!s}" for key in sorted(values, key=str)]
