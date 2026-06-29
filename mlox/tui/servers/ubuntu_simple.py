"""TUI setup form for pre-configured Ubuntu servers."""

from __future__ import annotations

from typing import Any

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure
from mlox.tui.template_forms import FormValues, TemplateFieldSpec

from .common import form_spec, native_fields, native_params


def setup_simple(_infra: Infrastructure, config: ServiceConfig):
    fields = native_fields()
    fields.extend(
        [
            TemplateFieldSpec(
                "private_key",
                "Private key",
                kind="multiline",
                required=False,
                help="Paste an SSH private key when password login is not available.",
            ),
            TemplateFieldSpec(
                "passphrase",
                "Private key passphrase",
                kind="password",
                required=False,
            ),
        ]
    )
    return form_spec(
        title=f"Add {config.name}",
        description="Connect to a server that already has remote access configured.",
        fields=fields,
        materialize=_simple_params,
    )


def _simple_params(values: FormValues, infra: Any) -> dict[str, str]:
    params = native_params(values, infra)
    params["${MLOX_ROOT_PRIVATE_KEY}"] = values.get("private_key", "")
    params["${MLOX_ROOT_PASSPHRASE}"] = values.get("passphrase", "")
    return params
