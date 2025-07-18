import json
import pandas as pd
import streamlit as st

from typing import cast, Dict

from mlox.infra import Infrastructure, Bundle
from mlox.services.gcp.sheet_service import GCPSpreadsheetsService
from mlox.secret_manager import AbstractSecretManagerService


def setup(infra: Infrastructure, bundle: Bundle) -> dict | None:
    params: Dict = dict()

    my_secret_manager_services = infra.filter_by_group("secret-manager")
    if len(my_secret_manager_services) == 0:
        st.error("No secret manager service found in the infrastructure.")
        return params

    c1, c2 = st.columns([30, 70])
    select_secret_manager_service = c1.selectbox(
        "Select Secret Manager Service",
        my_secret_manager_services,
        format_func=lambda x: x.name,
        key="secret_manager_service",
    )
    secret_name = c2.text_input(
        "Secret Name", value="MLOX_GCP_SHEETS_KEY", key="secret_name"
    )

    st.markdown("""
To access Google Spreadsheets do the following:
1. Go to google cloud console > APIs & Services and Enable Google Sheets API
2. In Google Sheets API go to Credentials > Create Credentials > Service Account
3. Click the created Service Account > Keys > Add Keys (Create New Key) > JSON
4. JSON key is automatically downloaded to your computer
    """)
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


def settings(infra: Infrastructure, bundle: Bundle, service: GCPSpreadsheetsService):
    # st.header(f"Settings for service {service.name}")
    # st.write(f"UUID: {service.secret_manager_uuid}")

    sheets = service.get_sheets(infra)
    st.write(sheets.list_spreadsheets())
