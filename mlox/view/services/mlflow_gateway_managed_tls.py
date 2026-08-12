"""Streamlit setup for the secret-manager-backed k3s gateway variant."""

from __future__ import annotations

from typing import cast

import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.service import AbstractSecretManagerService
from mlox.view.services.mlflow_gateway import setup as gateway_setup
from mlox.view.services.mlflow_gateway import settings

__all__ = ["settings", "setup"]


def setup(infra: Infrastructure, bundle: Bundle) -> dict | None:
    params = gateway_setup(infra, bundle)
    if params is None:
        return None

    managers = [
        service
        for service in infra.filter_by_group("secret-manager")
        if isinstance(service, AbstractSecretManagerService)
    ]
    if not managers:
        st.warning("No secret-manager service is available.")
        return None

    hostname = st.text_input(
        "TLS hostname",
        placeholder="gateway.example.org",
        key="mlflow_gateway_tls_hostname",
    )
    manager_service = st.selectbox(
        "TLS secret manager",
        managers,
        format_func=lambda service: service.name,
        key="mlflow_gateway_tls_manager",
    )
    try:
        manager = cast(
            AbstractSecretManagerService, manager_service
        ).get_secret_manager(infra)
        secret_names = sorted(manager.list_secrets(keys_only=True))
    except Exception as exc:
        st.warning(f"Could not list TLS secrets: {exc}")
        return None
    if not secret_names:
        st.warning("The selected secret manager does not contain any secrets.")
        return None
    secret_name = st.selectbox(
        "TLS secret",
        secret_names,
        key="mlflow_gateway_tls_secret",
    )

    params.update(
        {
            "${TLS_HOSTNAME}": hostname,
            "${TLS_SECRET_MANAGER_UUID}": manager_service.uuid,
            "${TLS_SECRET_NAME}": secret_name,
        }
    )
    return params
