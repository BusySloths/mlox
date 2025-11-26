"""Streamlit UI helpers for the OpenBao service."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from mlox.infra import Infrastructure, Bundle
from mlox.services.utils_ui import save_to_secret_store
from mlox.utils import generate_password

from .docker import OpenBaoDockerService


def _format_secret_value(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps(value, indent=2)
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, default=str)


def setup(infra: Infrastructure, bundle: Bundle):
    """Provide a predictable, punctuation-free root token."""
    params: dict[str, str] = {}

    suggested_token = generate_password(length=20, with_punctuation=False)
    # root_token = st.text_input("Root Token", value=suggested_token)

    params["${OPENBAO_ROOT_TOKEN}"] = suggested_token.strip()
    return params


def settings(infra: Infrastructure, bundle: Bundle, service: OpenBaoDockerService):
    key = f"openbao_secret_manager_{service.uuid}"
    if key not in st.session_state:
        st.session_state[key] = service.get_secret_manager(infra)
    manager = st.session_state[key]

    st.markdown("### Login Details")
    st.write(f"Root Token: `{service.root_token}`")
    st.write("Namespace: `root`")

    secrets = manager.list_secrets(keys_only=True)

    df = pd.DataFrame(
        [[name, "****"] for name in secrets.keys()], columns=["Key", "Value"]
    )
    selection = st.dataframe(
        df,
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
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
