"""TUI setup handlers for server templates."""

from __future__ import annotations

import getpass
import importlib

from mlox.ui.registry import register

_TUI_SERVER_BINDINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "mlox.tui.servers.ubuntu": {
        "config_ids": (
            "ubuntu-native-24.04-server",
            "ubuntu-docker-24.04-server",
        ),
        "function_names": ("setup_native",),
    },
    "mlox.tui.servers.ubuntu_simple": {
        "config_ids": ("ubuntu-simple-24.04-server",),
        "function_names": ("setup_simple",),
    },
    "mlox.tui.servers.ubuntu_k3s": {
        "config_ids": ("ubuntu-k3s-24.04-server",),
        "function_names": ("setup_k3s",),
    },
    "mlox.tui.servers.multipass": {
        "config_ids": (
            "ubuntu-multipass-native-24.04-server",
            "ubuntu-multipass-docker-24.04-server",
        ),
        "function_names": ("setup_multipass",),
    },
    "mlox.tui.servers.multipass_k3s": {
        "config_ids": ("ubuntu-multipass-k3s-24.04-server",),
        "function_names": ("setup_multipass_k3s",),
    },
    "mlox.tui.servers.connector": {
        "config_ids": ("connector-server",),
        "function_names": ("setup_connector",),
    },
    "mlox.tui.servers.local": {
        "config_ids": ("local-server",),
        "function_names": ("setup_local",),
    },
}


def register_builtin_tui_servers() -> None:
    """Register built-in server setup handlers for the Textual frontend."""

    for module_path, binding in _TUI_SERVER_BINDINGS.items():
        module = importlib.import_module(module_path)
        function_name = binding["function_names"][0]
        handler = getattr(module, function_name, None)
        if handler is None:
            continue
        for config_id in binding["config_ids"]:
            register(
                config_id=config_id,
                frontend="tui",
                function_name="setup",
                handler=handler,
            )


def current_username() -> str:
    """Return the current username with a stable fallback for setup defaults."""

    try:
        return getpass.getuser()
    except Exception:
        return "root"
