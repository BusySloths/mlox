import pandas as pd

import streamlit as st

from typing import cast

from mlox.infra import Infrastructure
from mlox.secret_manager import AbstractSecretManagerService


def secrets():
    st.markdown("""
    # Secret Manager
    - Keys and secrets
    - Configurations
    """)

    infra = cast(Infrastructure, st.session_state.mlox.infra)

    secret_manager_service = st.selectbox(
        "Choose Secret Manager Backend",
        infra.filter_by_group("secret-manager"),
        format_func=lambda x: f"{x.name}",
    )

    bundle = infra.get_bundle_by_service(secret_manager_service)
    if not bundle:
        st.error("Could not find server for secret manager.")
        return

    secret_manager = secret_manager_service.get_secret_manager(bundle.server)
    # secret_manager = st.session_state.mlox.secrets

    secrets = secret_manager.list_secrets(keys_only=False)
    with st.form("Add Secret"):
        name = st.text_input("Key")
        value = st.text_area("Value")
        if st.form_submit_button("Add Secret"):
            secret_manager.save_secret(name, value)
            st.rerun()

    df = pd.DataFrame(
        [[k, str(v)] for k, v in secrets.items()], columns=["Key", "Value"]
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
        key = df.iloc[idx]["Key"]
        st.write(secrets[key])


secrets()
