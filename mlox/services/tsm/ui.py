import pandas as pd
import streamlit as st

from typing import Dict

from mlox.services.tsm.service import TSMService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: TSMService):
    tsm = service.get_secret_manager(infra)
    secrets = tsm.list_secrets(keys_only=True)

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
        value = tsm.load_secret(key)
        with st.container(border=True):
            st.markdown(f"### `{key}`")
            # Display the secret value, but mask it
            if st.toggle(
                "Tree View",
                value=False,
                disabled=not isinstance(value, Dict),
                key=f"show_secret_{key}",
            ):
                st.write(value)
            else:
                my_secret = st.text_area(
                    "Value",
                    value=value,
                    height=200,
                    disabled=True,
                    key=f"secret_{key}",
                )
                if my_secret:
                    st.download_button(
                        "Download",
                        data=my_secret,
                        file_name=f"{key.lower()}.json",
                        mime="application/json",
                        icon=":material/download:",
                    )

    with st.form("Add Secret"):
        name = st.text_input("Key")
        value = st.text_area("Value")
        if st.form_submit_button("Add Secret"):
            tsm.save_secret(name, value)
            st.rerun()
