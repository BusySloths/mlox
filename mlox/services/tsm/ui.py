import pandas as pd
import streamlit as st

from typing import Dict, Any

from mlox.infra import Infrastructure, Bundle
from mlox.services.tsm.service import TSMService
from mlox.services.utils_ui import save_to_secret_store

from mlox.utils import generate_pw, dataclass_to_dict, encrypt_dict
from mlox.server import AbstractServer


def download_keyfile(server: AbstractServer, service: TSMService):
    if st.toggle(
        "Download Keyfile",
        value=False,
        key=f"download_keyfile_{service.name}",
        help="Download the keyfile for this service. It contains the secrets and server information.",
    ):
        c1, c2 = st.columns(2)
        keyfile_name = c1.text_input("Keyfile Name", value=f"{service.name}.json")
        keyfile_pw = c2.text_input("Password", value=generate_pw(16))

        keyfile_dict: Dict[str, Any] = {}
        keyfile_dict["secrets_path"] = service.get_absolute_path()
        keyfile_dict["secrets_pw"] = service.pw
        keyfile_dict["server"] = dataclass_to_dict(server)
        encrypted_keyfile_dict = encrypt_dict(keyfile_dict, keyfile_pw)

        st.download_button(
            "Download Keyfile",
            data=encrypted_keyfile_dict,
            file_name=keyfile_name,
            mime="application/json",
            icon=":material/download:",
        )


def settings(infra: Infrastructure, bundle: Bundle, service: TSMService):
    tsm = service.get_secret_manager(infra)
    secrets = tsm.list_secrets(keys_only=True)
    download_keyfile(bundle.server, service)

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
        if not value:
            st.info("Could not load secret.")
        else:
            save_to_secret_store(infra, key, value)

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
    else:
        with st.form("Add Secret"):
            name = st.text_input("Key")
            value = st.text_area("Value")
            if st.form_submit_button("Add Secret"):
                tsm.save_secret(name, value)
                st.rerun()
