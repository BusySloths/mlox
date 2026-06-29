"""TUI setup form for localhost servers."""

from __future__ import annotations

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure
from mlox.tui.template_forms import FormValues, TemplateFieldSpec

from . import current_username
from .common import form_spec


def setup_local(_infra: Infrastructure, config: ServiceConfig):
    return form_spec(
        title=f"Add {config.name}",
        description="Use the current machine as a local development backend.",
        fields=[
            TemplateFieldSpec("user", "Local user", default=current_username()),
            TemplateFieldSpec(
                "password",
                "Local password",
                kind="password",
                required=False,
            ),
        ],
        materialize=_local_params,
    )


def _local_params(values: FormValues, _infra: Infrastructure) -> dict[str, str]:
    return {
        "${MLOX_USER}": values.get("user", ""),
        "${MLOX_USER_PW}": values.get("password", ""),
    }
