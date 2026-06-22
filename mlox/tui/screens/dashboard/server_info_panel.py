"""Runtime server information panel."""

from __future__ import annotations

from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static

from mlox.application.use_cases.servers import get_server_runtime_info

from .model import SelectionInfo


class ServerInfoPanel(Container):
    """Display and cache runtime information for selected servers."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    def __init__(self, *children, **kwargs) -> None:
        super().__init__(*children, **kwargs)
        self._cache: dict[int, str] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="server-info-controls"):
            yield Button("Refresh", id="refresh-server-info", variant="primary")
        yield Static(
            "Select a server and press Refresh to load runtime information.",
            id="server-runtime-info",
            markup=False,
        )

    def on_mount(self) -> None:
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return

        server = self._selected_server(selection)
        output = self.query_one("#server-runtime-info", Static)
        if not server:
            output.update(
                "Select a server and press Refresh to load runtime information."
            )
            self.query_one("#refresh-server-info", Button).disabled = True
            return

        self.query_one("#refresh-server-info", Button).disabled = False
        cached = self._cache.get(self._cache_key(server))
        if cached is not None:
            output.update(cached)
            return

        output.update("Press Refresh to load runtime information.")

    @on(Button.Pressed, "#refresh-server-info")
    def handle_refresh(self, _: Button.Pressed) -> None:
        self.load_selected_server_info(refresh=True)

    def load_selected_server_info(self, *, refresh: bool = False) -> bool:
        """Show cached information or load it in the background."""

        server = self._selected_server(self.selection)
        if not server:
            return False

        cache_key = self._cache_key(server)
        cached = self._cache.get(cache_key)
        output = self.query_one("#server-runtime-info", Static)
        if cached is not None and not refresh:
            output.update(cached)
            return True

        self.query_one("#refresh-server-info", Button).disabled = True
        output.update("Loading server information...")

        def load_server_info() -> None:
            try:
                result = get_server_runtime_info(server)
                self.app.call_from_thread(
                    self._show_server_info_result,
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
                        server,
                        f"Failed to load server information: {exc}",
                    )
                except Exception:
                    pass

        self.app.run_worker(
            load_server_info,
            thread=True,
            exclusive=True,
            group="server-info",
        )
        return True

    def _show_server_info_result(self, server: object, result) -> None:
        if server is not self._selected_server(self.selection):
            return

        self.query_one("#refresh-server-info", Button).disabled = False
        if not result.success:
            self.notify(result.message, severity="error")
            self.query_one("#server-runtime-info", Static).update("")
            return

        rendered = self._format_runtime_info(result.data or {})
        self._cache[self._cache_key(server)] = rendered
        self.query_one("#server-runtime-info", Static).update(rendered)

    def _show_server_info_error(self, server: object, message: str) -> None:
        if server is not self._selected_server(self.selection):
            return

        self.query_one("#refresh-server-info", Button).disabled = False
        self.query_one("#server-runtime-info", Static).update(message)
        self.notify(message, severity="error")

    def _selected_server(self, selection: Optional[SelectionInfo]) -> object | None:
        server = selection.server if selection else None
        if not server and selection:
            server = getattr(selection.bundle, "server", None)
        return server

    def _cache_key(self, server: object) -> int:
        return id(server)

    def _format_runtime_info(self, data: dict) -> str:
        sections: list[str] = []
        server_info = data.get("server_info") or {}
        backend_info = data.get("backend_info") or {}
        errors = data.get("errors") or []

        sections.append("Server")
        sections.extend(self._format_mapping(server_info))
        sections.append("")
        sections.append("Backend")
        sections.extend(self._format_mapping(backend_info))
        if errors:
            sections.append("")
            sections.append("Errors")
            sections.extend(str(error) for error in errors)
        return "\n".join(sections)

    def _format_mapping(self, values: object) -> list[str]:
        if not isinstance(values, dict) or not values:
            return ["-"]
        return [f"{key}: {values[key]!s}" for key in sorted(values, key=str)]
