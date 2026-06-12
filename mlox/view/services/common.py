import json
import streamlit as st

from collections.abc import Callable
from typing import Any, Dict
from mlox.infra import Infrastructure
from mlox.secret_manager import AbstractSecretManager

from mlox.view.utils import st_hack_align


def dedicated_secret_manager_settings(handler: Callable) -> Callable:
    """Mark a service settings handler for display on the secret-manager page."""
    handler.is_secret_manager_settings = True
    return handler


def commit_project():
    with st.spinner("Saving project..."):
        st.session_state.mlox.commit()


def save_to_secret_store(infra: Infrastructure, secret_name: str, secrets: Dict | str):
    st.markdown(
        """Save Secrets to Secret Manager. This allows you to save secrets to the secret manager for later use"""
    )
    workspace = st.session_state.mlox
    sm = workspace.secrets
    if not sm.is_working():
        st.error("The active secret manager is unavailable.")
        return

    c1, c2 = st.columns([70, 30])
    c1.text_input(
        "Active Secret Manager",
        value=type(sm).__name__,
        disabled=True,
        key=f"secret-manager-{secret_name}",
    )

    st_hack_align(c2)
    if c2.button("Save Secrets", key=f"save-secret-{secret_name}"):
        with st.spinner(f"Saving '{secret_name}' to secret store..."):
            sm.save_secret(secret_name, secrets)
            st.success(f"Secrets '{secret_name}' saved successfully.")


def _format_secret_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, default=str)


def render_secret_manager_settings(
    manager: AbstractSecretManager,
    *,
    key_prefix: str,
) -> None:
    """Render the common secret browser for any secret-manager implementation."""
    try:
        secret_names = sorted(manager.list_secrets(keys_only=True))
    except Exception as exc:
        st.warning(f"Could not list secrets: {exc}")
        return

    table = [{"Key": name, "Value": "****"} for name in secret_names]
    selection = st.dataframe(
        table,
        hide_index=True,
        selection_mode="single-row",
        width="stretch",
        on_select="rerun",
        key=f"{key_prefix}-secrets-table",
    )
    selected_rows = selection.get("selection", {}).get("rows", [])
    if selected_rows:
        secret_name = secret_names[selected_rows[0]]
        try:
            value = manager.load_secret(secret_name)
        except Exception as exc:
            st.warning(f"Could not load secret: {exc}")
            return
        if value is None:
            st.info("Could not load secret.")
            return

        formatted = _format_secret_value(value)
        with st.container(border=True):
            st.markdown(f"### `{secret_name}`")
            if isinstance(value, (dict, list)) and st.toggle(
                "Tree View",
                value=False,
                key=f"{key_prefix}-tree-{secret_name}",
            ):
                st.write(value)
            else:
                st.text_area(
                    "Value",
                    value=formatted,
                    height=240,
                    disabled=True,
                    key=f"{key_prefix}-value-{secret_name}",
                )
            st.download_button(
                "Download",
                data=formatted,
                file_name=f"{secret_name.lower()}.json",
                mime="application/json",
                icon=":material/download:",
                key=f"{key_prefix}-download-{secret_name}",
            )
        return

    if not secret_names:
        st.info("This secret manager does not contain any secrets.")

    with st.form(f"{key_prefix}-add-secret"):
        name = st.text_input("Key")
        value = st.text_area("Value", placeholder="JSON or text")
        if st.form_submit_button("Add Secret"):
            if not name.strip():
                st.error("A secret key is required.")
            else:
                manager.save_secret(name.strip(), value)
                st.rerun()
