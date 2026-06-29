"""TUI setup form for Ubuntu k3s servers."""

from __future__ import annotations

from typing import Any

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure
from mlox.tui.template_forms import FormValues

from .common import add_k3s_params, form_spec, k3s_controller_field, native_fields, native_params


def setup_k3s(infra: Infrastructure, config: ServiceConfig):
    return form_spec(
        title=f"Add {config.name}",
        description="Create a new k3s controller or join this server to an existing controller.",
        fields=native_fields() + [k3s_controller_field(infra)],
        materialize=_k3s_params,
    )


def _k3s_params(values: FormValues, infra: Any) -> dict[str, str]:
    return add_k3s_params(values, infra, native_params(values, infra))
