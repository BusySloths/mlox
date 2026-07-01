from __future__ import annotations

import importlib

from mlox.ui.registry import register

_REGISTERED = False

_TUI_SERVICE_BINDINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "mlox.tui.services.otel": {
        "config_ids": ("otel-0.127.0-docker", "otel-0.146.1-docker"),
        "function_names": ("settings",),
    },
    "mlox.tui.services.openbao": {
        "config_ids": ("openbao-docker",),
        "function_names": ("settings",),
    },
}


def register_builtin_tui_services() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    _REGISTERED = True
    for module_path, binding in _TUI_SERVICE_BINDINGS.items():
        module = importlib.import_module(module_path)
        for function_name in binding["function_names"]:
            handler = getattr(module, function_name, None)
            if handler is None:
                continue
            for config_id in binding["config_ids"]:
                register(
                    config_id=config_id,
                    frontend="tui",
                    function_name=function_name,
                    handler=handler,
                )
