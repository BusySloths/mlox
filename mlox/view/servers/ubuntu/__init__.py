from __future__ import annotations

import importlib

from mlox.ui.registry import register

_REGISTERED = False

_STREAMLIT_SERVER_BINDINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "mlox.view.servers.ubuntu.multipass": {
        "config_ids": (
            "ubuntu-multipass-native-24.04-server",
            "ubuntu-multipass-docker-24.04-server",
        ),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.servers.ubuntu.multipass_k3s": {
        "config_ids": ("ubuntu-multipass-k3s-24.04-server",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.servers.ubuntu.docker": {
        "config_ids": ("ubuntu-docker-24.04-server",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.servers.ubuntu.k3s": {
        "config_ids": ("ubuntu-k3s-24.04-server",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.servers.ubuntu.native": {
        "config_ids": ("ubuntu-native-24.04-server",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.servers.ubuntu.simple": {
        "config_ids": ("ubuntu-simple-24.04-server",),
        "function_names": ("settings", "setup"),
    },
}


def register_builtin_streamlit_servers() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    for module_path, binding in _STREAMLIT_SERVER_BINDINGS.items():
        module = importlib.import_module(module_path)
        for function_name in binding["function_names"]:
            handler = getattr(module, function_name, None)
            if handler is None:
                continue
            for config_id in binding["config_ids"]:
                register(
                    config_id=config_id,
                    frontend="streamlit",
                    function_name=function_name,
                    handler=handler,
                )

    _REGISTERED = True
