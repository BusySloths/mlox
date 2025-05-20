import pandas as pd

import streamlit as st


def secrets():
    st.markdown("""
    # Outputs
    This is the collections of all the outputs of your MLOps stack to be used in your applications.:
    - Keys and secrets
    - Configurations
    """)

    ip = "<IP_ADDRESS>"
    gcp_prj = "<GCP_PROJECT_ID>"
    st.selectbox(
        "Choose Secret Manager Backend",
        [
            "Local (not recommended)",
            f"OpenBAO on {ip}",
            f"Google Secret Manager for Project {gcp_prj}",
        ],
    )

    ms = st.session_state.mlox
    secrets = ms.secrets.list_secrets(keys_only=False)
    with st.form("Add Secret"):
        name = st.text_input("Key")
        value = st.text_area("Value")
        if st.form_submit_button("Add Secret"):
            ms.secrets.save_secret(name, value)
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
