"""Inline runtime information panels for server and bundle selections."""

from __future__ import annotations

from typing import Any, Optional

from rich.console import Group
from rich.table import Table
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static

from mlox.application.use_cases.servers import get_backend_info, get_server_info

from .model import SelectionInfo


class ServerInfoPanel(Container):
    """Display and cache runtime server/backend information."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._cache: dict[tuple[str, int], Any] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="server-info-controls"):
            yield Button("Refresh", id="refresh-server-info", variant="primary")
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
        if not self.display:
            return

        title = self.query_one("#refresh-server-info", Button)
        server = self._selected_server(selection)
        output = self.query_one("#server-runtime-info", Static)
        if not server:
            output.update(
                "Select a server or bundle to load runtime information."
            )
            title.disabled = True
            return

        title.disabled = False
        cached = self._cache.get(self._cache_key(selection, server))
        if cached is not None:
            output.update(cached)
            return

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
            output.update(cached)
            return True

        self.query_one("#refresh-server-info", Button).disabled = True
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
            self.query_one("#server-runtime-info", Static).update("")
            return

        rendered = self._format_runtime_info(selection, result.data or {})
        self._cache[self._cache_key(selection, server)] = rendered
        self.query_one("#server-runtime-info", Static).update(rendered)

    def _show_server_info_error(
        self, selection: Optional[SelectionInfo], server: object, message: str
    ) -> None:
        if selection != self.selection or server is not self._selected_server(self.selection):
            return

        self.query_one("#refresh-server-info", Button).disabled = False
        self.query_one("#server-runtime-info", Static).update(message)
        self.notify(message, severity="error")

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
    ) -> str:
        sections: list[str] = []
        if selection and selection.type == "bundle":
            sections.append("Backend")
            backend_info = data.get("backend_info") or {}
            docker_table = self._format_docker_backend(backend_info)
            if docker_table is not None:
                return docker_table
            sections.extend(self._format_mapping(backend_info))
        else:
            sections.append("Server")
            sections.extend(self._format_mapping(data.get("server_info") or {}))
        return "\n".join(sections)

    def _format_docker_backend(self, backend_info: object) -> Group | None:
        if not isinstance(backend_info, dict):
            return None
        if not any(str(key).startswith("docker.") for key in backend_info):
            return None

        summary = Table(title="Docker Backend", show_header=True, header_style="bold")
        summary.add_column("Metric", style="cyan", no_wrap=True)
        summary.add_column("Value")
        summary.add_row(
            "Backend Running",
            self._format_bool(backend_info.get("backend.is_running")),
        )
        summary.add_row(
            "Docker Running",
            self._format_bool(backend_info.get("docker.is_running")),
        )
        summary.add_row(
            "Docker Enabled",
            self._format_bool(backend_info.get("docker.is_enabled")),
        )
        summary.add_row(
            "Client Version",
            self._docker_version(backend_info.get("docker.version"), "Client"),
        )
        summary.add_row(
            "Server Version",
            self._docker_version(backend_info.get("docker.version"), "Server"),
        )

        containers = backend_info.get("docker.containers")
        if not isinstance(containers, list):
            summary.add_row("Containers", str(containers or "-"))
            return Group(summary)

        summary.add_row("Containers", str(len(containers)))
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

        return Group(summary, container_table)

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
