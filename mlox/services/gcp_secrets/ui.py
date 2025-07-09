import json
import pandas as pd
import streamlit as st

from typing import cast, Dict

from mlox.services.gcp_secrets.service import GCPSecretsService
from mlox.infra import Infrastructure, Bundle
from mlox.secret_manager import AbstractSecretManagerService


def setup(infra: Infrastructure, bundle: Bundle) -> dict:
    params: Dict = dict()

    my_secret_manager_services = infra.filter_by_group("secret-manager")
    if len(my_secret_manager_services) == 0:
        st.error("No secret manager service found in the infrastructure.")
        return params

    select_secret_manager_service = st.selectbox(
        "Select Secret Manager Service",
        my_secret_manager_services,
        format_func=lambda x: x.name,
        key="secret_manager_service",
    )
    secret_name = st.text_input(
        "Secret Name", value="MLOX_GCP_SECRET_MANAGER_KEY", key="secret_name"
    )

    keyfile_dict = st.text_area(
        "Add the contents of your service account keyfile.json here"
    )

    is_keyfile_dict = False
    try:
        keyfile_dict = json.loads(keyfile_dict)
        is_keyfile_dict = True
    except Exception as e:  # noqa: BLE001
        st.info(f"Invalid JSON format. Please provide a valid JSON object. ")

    if hasattr(select_secret_manager_service, "get_secret_manager"):
        sms = cast(AbstractSecretManagerService, select_secret_manager_service)
        sm = sms.get_secret_manager(infra)
        if st.button("Save Secret", type="primary", disabled=not is_keyfile_dict):
            sm.save_secret(secret_name, keyfile_dict)

    params["${SECRET_MANAGER_UUID}"] = select_secret_manager_service.uuid
    params["${SECRET_NAME}"] = secret_name

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: GCPSecretsService):
    st.header(f"Settings for service {service.name}")

    st.write(f"UUID: {service.secret_manager_uuid}")

    tsm = service.get_secret_manager(infra)
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
