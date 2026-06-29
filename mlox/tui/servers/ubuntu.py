"""TUI setup form for Ubuntu native-style servers."""

from __future__ import annotations

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure

from .common import form_spec, native_fields, native_params


def setup_native(_infra: Infrastructure, config: ServiceConfig):
    return form_spec(
        title=f"Add {config.name}",
        description="Connect to an existing Ubuntu server with SSH credentials.",
        fields=native_fields(),
        materialize=native_params,
    )
