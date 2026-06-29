from __future__ import annotations

import importlib
import logging

from typing import Callable

logger = logging.getLogger(__name__)

_REGISTRY: dict[tuple[str, str, str], Callable] = {}
_BOOTSTRAPPED = False


def register(
    *,
    config_id: str,
    frontend: str,
    function_name: str,
    handler: Callable,
) -> None:
    """Register a UI handler for a config ID and frontend namespace."""

    _REGISTRY[(frontend, function_name, config_id)] = handler


def get_handler(
    *,
    config_id: str,
    frontend: str,
    function_name: str,
) -> Callable | None:
    _ensure_bootstrapped()
    return _REGISTRY.get((frontend, function_name, config_id))


def clear_handlers(*, bootstrapped: bool = False) -> None:
    """Reset the registry.

    This is primarily intended for tests that want a controlled registry state.
    """

    global _BOOTSTRAPPED
    _REGISTRY.clear()
    _BOOTSTRAPPED = bootstrapped


def _ensure_bootstrapped() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    had_error = False
    for module_path, register_name in (
        ("mlox.view.services", "register_builtin_streamlit_services"),
        ("mlox.view.servers.ubuntu", "register_builtin_streamlit_servers"),
        ("mlox.view.servers.connector", "register_builtin_streamlit_servers"),
        ("mlox.tui.services", "register_builtin_tui_services"),
        ("mlox.tui.servers", "register_builtin_tui_servers"),
    ):
        try:
            module = importlib.import_module(module_path)
            register_builtin = getattr(module, register_name)
            register_builtin()
        except Exception as exc:  # pragma: no cover - defensive bootstrap logging
            had_error = True
            logger.exception(
                "Failed to bootstrap UI registrations from %s: %s",
                module_path,
                exc,
            )

    _BOOTSTRAPPED = not had_error
