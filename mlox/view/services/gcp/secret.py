import json
import logging
import streamlit as st

from typing import cast, Dict

from mlox.services.gcp.secret_service import GCPSecretService
from mlox.infra import Infrastructure, Bundle
from mlox.service import AbstractSecretManagerService
from mlox.view.services.common import render_secret_manager_settings

logger = logging.getLogger(__name__)


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
        key="gcp_secret_manager_service",
    )
    secret_name = c2.text_input(
        "Secret Name", value="MLOX_GCP_SECRET_MANAGER_KEY", key="gcp_secret_name"
    )

    st.markdown("""
To access the secret manager, a service account with the following roles are necessary:
1. secret manager secret accessor (view and read secret contents)
2. secret manager viewer (list secrets)
3. secret manager admin (create and update secrets and versions)
            """)
    keyfile_dict = st.text_area(
        "Add the contents of your service account keyfile.json here",
        key="gcp_keyfile_json",
    )
    is_keyfile_dict = False
    try:
        keyfile_dict = json.loads(keyfile_dict)
        is_keyfile_dict = True
    except Exception as e:  # noqa: BLE001
        st.info("Invalid JSON format. Please provide a valid JSON object. ")
        logger.warning(f"Invalid JSON format for keyfile: {e}")

    if hasattr(select_secret_manager_service, "get_secret_manager"):
        sms = cast(AbstractSecretManagerService, select_secret_manager_service)
        sm = sms.get_secret_manager(infra)
        if st.button(
            "Save Secret",
            type="primary",
            disabled=not is_keyfile_dict,
            key="gcp_save_secret",
        ):
            sm.save_secret(secret_name, keyfile_dict)

    params["${SECRET_MANAGER_UUID}"] = select_secret_manager_service.uuid
    params["${SECRET_NAME}"] = secret_name

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: GCPSecretService):
    sm = service.get_secret_manager(infra)
    render_secret_manager_settings(
        sm, key_prefix=f"gcp-secret-manager-{service.uuid}"
    )
