import streamlit as st

from typing import Dict, cast
from mlox.infra import Infrastructure
from mlox.secret_manager import AbstractSecretManagerService

from mlox.view.utils import st_hack_align


def save_infrastructure():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


def save_to_secret_store(infra: Infrastructure, secret_name: str, secrets: Dict):
    st.markdown(
        """Save Secrets to Secret Manager. This allows you to save secrets to the secret manager for later use"""
    )
    sms = infra.filter_by_group("secret-manager")
    if not sms:
        st.info("No secret manager found in the infrastructure.")
        return

    c1, c2 = st.columns([70, 30])
    select_sms = c1.selectbox(
        "Select Secret Manager",
        sms,
        format_func=lambda s: f"{s.name}",
        key="secret_manager",
    )
    if not select_sms:
        return

    if not hasattr(select_sms, "get_secret_manager"):
        st.error("Selected item is not a valid secret manager.")
        return
    cast_select_sms = cast(AbstractSecretManagerService, select_sms)
    sm = cast_select_sms.get_secret_manager(infra)
    if not sm or not sm.is_working():
        st.error("Secret manager is not working. Please check the configuration.")
        return

    st_hack_align(c2)
    if c2.button("Save Secrets"):
        with st.spinner(f"Saving '{secret_name}' to secret store..."):
            sm.save_secret(secret_name, secrets)
            st.success(f"Secrets '{secret_name}' saved successfully.")
