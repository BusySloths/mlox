"""Inline runtime information panels for server and bundle selections."""

from __future__ import annotations

from typing import Any, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Static

from mlox.application.use_cases.servers import get_backend_info, get_server_info

from .model import SelectionInfo
from .runtime_formatters import RuntimeInfoDisplay, format_runtime_info


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

    def _show_info_result(
        self, selection: Optional[SelectionInfo], server: object, result
    ) -> None:
        if selection != self.selection or server is not self._selected_server(
            self.selection
        ):
            return

        self.query_one("#refresh-server-info", Button).disabled = False
        if not result.success:
            self.notify(result.message, severity="error")
            self.query_one("#server-info-summary", Static).update("")
            self.query_one("#server-runtime-info", Static).update("")
            return

        rendered = format_runtime_info(
            selection.type if selection else None,
            result.data or {},
        )
        self._cache[self._cache_key(selection, server)] = rendered
        self._show_runtime_display(rendered)

    def _show_server_info_error(
        self, selection: Optional[SelectionInfo], server: object, message: str
    ) -> None:
        if selection != self.selection or server is not self._selected_server(
            self.selection
        ):
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

    def _cache_key(
        self, selection: Optional[SelectionInfo], server: object
    ) -> tuple[str, int]:
        mode = selection.type if selection else "server"
        return (mode, id(server))

    def _load_info(self, selection: Optional[SelectionInfo], server: object):
        if selection and selection.type == "bundle":
            return get_backend_info(server)
        return get_server_info(server)

    def _render_title(self, selection: Optional[SelectionInfo]) -> None:
        if selection and selection.type == "bundle":
            self.border_title = "Backend"
            return
        if selection and selection.type == "server":
            self.border_title = "Server Info"
            return
        self.border_title = "Runtime Info"

    def _empty_message(self, selection: Optional[SelectionInfo]) -> str:
        if selection and selection.type == "bundle":
            return "Press Refresh to load backend information."
        return "Press Refresh to load server information."

    def _loading_message(self, selection: Optional[SelectionInfo]) -> str:
        if selection and selection.type == "bundle":
            return "Loading backend information..."
        return "Loading server information..."
