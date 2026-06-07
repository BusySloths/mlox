from __future__ import annotations

from typing import Any

import streamlit as st

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure
from mlox.ui.registry import register
from mlox.utils import generate_password

_REGISTERED = False


def _generate_connector_name(infra: Infrastructure) -> str:
    existing_names = {bundle.server.ip for bundle in infra.bundles}
    while True:
        name = f"mlox-connector-{generate_password(8).lower()}"
        if name not in existing_names:
            return name


def setup(infra: Infrastructure, config: ServiceConfig) -> dict[str, Any] | None:
    """Collect the logical name used to identify a virtual connector backend."""

    connector_count = len(infra.filter_bundles_by_backend("connector"))
    name = st.text_input(
        "Connector name",
        value=_generate_connector_name(infra),
        help=(
            "Unique logical name for this virtual backend. It is used for MLOX "
            "lookups only and is not a hostname or IP address."
        ),
        key=f"setup-connector-name-{config.id}-{connector_count}",
    ).strip()

    if not name:
        st.warning("Enter a connector name.")
        return None
    if infra.get_bundle_by_ip(name):
        st.warning("A server with this name already exists.")
        return None

    return {"${MLOX_IP}": name}


def register_builtin_streamlit_servers() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    register(
        config_id="connector-server",
        frontend="streamlit",
        function_name="setup",
        handler=setup,
    )
    _REGISTERED = True
