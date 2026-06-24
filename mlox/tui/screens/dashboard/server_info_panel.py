"""Inline runtime information panels for server and bundle selections."""

from __future__ import annotations

from typing import Any, Optional

from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

from mlox.application.use_cases.servers import get_backend_info, get_server_info

from .model import SelectionInfo
from .runtime_formatters import format_runtime_info


class ServerInfoPanel(Static):
    """Display and cache runtime server/backend information."""

    selection: reactive[Optional[SelectionInfo]] = reactive(None)

    class RuntimeInfoLoadFinished(Message):
        """Runtime information loading has completed."""

    class RuntimeInfoLoadStarted(Message):
        """Runtime information loading has started."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("markup", False)
        super().__init__("", *args, **kwargs)
        self._cache: dict[tuple[str, int], Any] = {}

    def on_mount(self) -> None:
        self.watch_selection(self.selection)

    def watch_selection(self, selection: Optional[SelectionInfo]) -> None:
        if not self.is_mounted:
            return

        self._render_title(selection)
        if not selection or selection.type not in {"bundle", "server"}:
            self._hide_runtime_info()
            return

        server = self._selected_server(selection)
        if not server:
            self._hide_runtime_info()
            return

        cached = self._cache.get(self._cache_key(selection, server))
        if cached is not None:
            self._show_runtime_display(cached)
            return

        self._hide_runtime_info()

    def load_selected_info(self, *, refresh: bool = False) -> bool:
        """Show cached information or load it in the background."""

        selection = self.selection
        server = self._selected_server(selection)
        if not server:
            return False

        cache_key = self._cache_key(selection, server)
        cached = self._cache.get(cache_key)
        if cached is not None and not refresh:
            self._show_runtime_display(cached)
            return True

        self.post_message(self.RuntimeInfoLoadStarted())

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

        if not result.success:
            self.notify(result.message, severity="error")
            self._hide_runtime_info()
            self.post_message(self.RuntimeInfoLoadFinished())
            return

        rendered = format_runtime_info(
            selection.type if selection else None,
            result.data or {},
        )
        self._cache[self._cache_key(selection, server)] = rendered
        self._show_runtime_display(rendered)
        self.post_message(self.RuntimeInfoLoadFinished())

    def _show_server_info_error(
        self, selection: Optional[SelectionInfo], server: object, message: str
    ) -> None:
        if selection != self.selection or server is not self._selected_server(
            self.selection
        ):
            return

        self._hide_runtime_info()
        self.notify(message, severity="error")
        self.post_message(self.RuntimeInfoLoadFinished())

    def _hide_runtime_info(self) -> None:
        self.update("")
        self.display = False

    def _show_runtime_display(self, rendered: object) -> None:
        self.display = True
        self.update(rendered)

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
