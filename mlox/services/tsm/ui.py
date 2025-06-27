import pandas as pd
import streamlit as st

from mlox.services.tsm.service import TSMService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: TSMService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")
    st.write(f'Password: "{service.pw}"')

    tsm = service.get_secret_manager(bundle.server)
    secrets = tsm.list_secrets(keys_only=True)
    with st.form("Add Secret"):
        name = st.text_input("Key")
        value = st.text_area("Value")
        if st.form_submit_button("Add Secret"):
            tsm.save_secret(name, value)
            st.rerun()

    df = pd.DataFrame(
        [[k, "****"] for k, v in secrets.items()], columns=["Key", "Value"]
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
        st.write(tsm.load_secret(key))
