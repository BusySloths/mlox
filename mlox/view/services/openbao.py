"""Streamlit UI helpers for the OpenBao service."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from mlox.infra import Infrastructure, Bundle
from mlox.view.services.common import save_to_secret_store

from mlox.services.openbao import OpenBaoDockerService


def _format_secret_value(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, indent=2)
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, default=str)


def setup(infra: Infrastructure, bundle: Bundle):
    """OpenBao production mode bootstraps itself after the first start."""
    return {}


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def settings(infra: Infrastructure, bundle: Bundle, service: OpenBaoDockerService):
    key = f"openbao_secret_manager_{service.uuid}"
    if key not in st.session_state:
        st.session_state[key] = service.get_secret_manager(infra)
    manager = st.session_state[key]

    st.markdown("### Bootstrap")
    try:
        status = manager.seal_status()
    except Exception as exc:
        status = {}
        st.warning(f"Could not read OpenBao seal status: {exc}")

    initialized = bool(status.get("initialized", bool(service.root_token)))
    sealed = bool(status.get("sealed", False)) if status else False
    st.write(f"Initialized: `{initialized}`")
    st.write(f"Sealed: `{sealed}`")
    st.write(f"Root Token: `{_mask_secret(service.root_token)}`")
    if service.root_token and st.toggle(
        "Show full root token",
        value=False,
        key=f"openbao_show_root_token_{service.uuid}",
    ):
        st.text_input(
            "Root Token",
            value=service.root_token,
            disabled=True,
            type="default",
            key=f"openbao_root_token_{service.uuid}",
        )
    st.write(f"Unseal Keys: `{len(service.unseal_keys)}`")
    if service.unseal_keys and st.toggle(
        "Show unseal keys",
        value=False,
        key=f"openbao_show_unseal_keys_{service.uuid}",
    ):
        for idx, unseal_key in enumerate(service.unseal_keys, start=1):
            st.text_input(
                f"Unseal Key {idx}",
                value=unseal_key,
                disabled=True,
                type="default",
                key=f"openbao_unseal_key_{service.uuid}_{idx}",
            )
    st.write("Namespace: `root`")

    if sealed:
        if not service.unseal_keys:
            st.warning("OpenBao is sealed and no unseal key is stored in mlox state.")
            return
        if st.button(
            "Unseal",
            type="primary",
            icon=":material/lock_open:",
            key=f"openbao_unseal_{service.uuid}",
        ):
            for unseal_key in service.unseal_keys:
                status = manager.unseal(unseal_key)
                if not bool(status.get("sealed", True)):
                    break
            if bool(status.get("sealed", True)):
                st.error("OpenBao remained sealed after submitting stored unseal keys.")
            else:
                st.success("OpenBao unsealed.")
                st.rerun()
        return

    try:
        secrets = manager.list_secrets(keys_only=True)
    except Exception as exc:
        st.warning(f"Could not list OpenBao secrets: {exc}")
        return

    df = pd.DataFrame(
        [[name, "****"] for name in secrets.keys()], columns=["Key", "Value"]
    )
    selection = st.dataframe(
        df,
        hide_index=True,
        selection_mode="single-row",
        width="stretch",
        on_select="rerun",
    )

    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        secret_key = df.iloc[idx]["Key"]
        secret_value = manager.load_secret(secret_key)
        if secret_value is None:
            st.info("Could not load secret from OpenBao.")
        else:
            save_to_secret_store(infra, secret_key, secret_value)
            with st.container(border=True):
                st.markdown(f"### `{secret_key}`")
                if isinstance(secret_value, dict) and st.toggle(
                    "Tree View",
                    value=False,
                    key=f"openbao_tree_{secret_key}",
                ):
                    st.write(secret_value)
                else:
                    formatted = _format_secret_value(secret_value)
                    st.text_area(
                        "Value",
                        value=formatted,
                        height=240,
                        disabled=True,
                        key=f"openbao_value_{secret_key}",
                    )
                    if formatted:
                        st.download_button(
                            "Download",
                            data=formatted,
                            file_name=f"{secret_key.lower()}.json",
                            mime="application/json",
                            icon=":material/download:",
                            key=f"openbao_download_{secret_key}",
                        )
    else:
        with st.form("openbao_add_secret"):
            name = st.text_input("Key")
            value = st.text_area("Value", placeholder="JSON or text")
            if st.form_submit_button("Add Secret"):
                manager.save_secret(name, value)
                st.rerun()
