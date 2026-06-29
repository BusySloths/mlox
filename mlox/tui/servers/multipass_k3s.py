"""TUI setup form for Multipass k3s servers."""

from __future__ import annotations

import uuid
from typing import Any

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure
from mlox.tui.template_forms import FormValues

from .common import add_k3s_params, form_spec, k3s_controller_field, multipass_fields, multipass_params


def setup_multipass_k3s(infra: Infrastructure, config: ServiceConfig):
    fields = multipass_fields()
    fields[0].default = f"mlox-{uuid.uuid4().hex[:8]}"
    fields.append(k3s_controller_field(infra))
    return form_spec(
        title=f"Add {config.name}",
        description="Launch a Multipass VM as a new k3s controller or join an existing cluster.",
        fields=fields,
        materialize=_multipass_k3s_params,
    )


def _multipass_k3s_params(values: FormValues, infra: Any) -> dict[str, str]:
    return add_k3s_params(values, infra, multipass_params(values, infra))
