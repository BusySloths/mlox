import streamlit as st

from mlox.infra import Infrastructure, Bundle
from mlox.services.tsm.service import TSMService
from mlox.view.services.common import render_secret_manager_settings


def settings(infra: Infrastructure, bundle: Bundle, service: TSMService):
    # store secret manager in session to avoid recreating it on every rerun
    key = f"tsm_secret_manager_{service.uuid}"
    if key not in st.session_state:
        st.session_state[key] = service.get_secret_manager(infra)
    tsm = st.session_state[key]
    render_secret_manager_settings(tsm, key_prefix=f"tsm-{service.uuid}")
