"""TUI setup form for virtual connector backends."""

from __future__ import annotations

from mlox.config import ServiceConfig
from mlox.infra import Infrastructure
from mlox.tui.template_forms import FormValues, TemplateFieldSpec
from mlox.utils import generate_password

from .common import form_spec


def setup_connector(infra: Infrastructure, config: ServiceConfig):
    return form_spec(
        title=f"Add {config.name}",
        description="Create a logical backend for externally hosted connector services.",
        fields=[
            TemplateFieldSpec(
                "name",
                "Connector name",
                default=_generate_connector_name(infra),
            )
        ],
        materialize=_connector_params,
    )


def _generate_connector_name(infra: Infrastructure) -> str:
    existing = {
        getattr(getattr(bundle, "server", None), "ip", "")
        for bundle in getattr(infra, "bundles", []) or []
    }
    while True:
        name = f"mlox-connector-{generate_password(8).lower()}"
        if name not in existing:
            return name


def _connector_params(values: FormValues, _infra: Infrastructure) -> dict[str, str]:
    return {"${MLOX_IP}": values.get("name", "")}
