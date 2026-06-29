"""TUI setup form for Multipass-backed Ubuntu servers."""

from __future__ import annotations

import uuid

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure

from .common import form_spec, multipass_fields, multipass_params


def setup_multipass(_infra: Infrastructure, config: ServiceConfig):
    fields = multipass_fields()
    fields[0].default = f"mlox-{uuid.uuid4().hex[:8]}"
    return form_spec(
        title=f"Add {config.name}",
        description="Launch a local Ubuntu VM with Multipass and provision the selected backend.",
        fields=fields,
        materialize=multipass_params,
    )
