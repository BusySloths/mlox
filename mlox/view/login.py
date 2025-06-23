import os
import streamlit as st

from mlox.services.tsm.service import TSMService
from mlox.session import MloxSession
from mlox.config import load_all_server_configs, load_config
from mlox.infra import Infrastructure
from mlox.utils import dataclass_to_dict, save_to_json


def login():
    with st.form("login"):
        username = st.text_input("Username", value="mlox")
        password = st.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        submitted = st.form_submit_button("Login")
        if submitted:
            ms = None
            try:
                ms = MloxSession(username, password)
                if ms.secrets.is_working():
                    st.session_state["mlox"] = ms
                    st.session_state.is_logged_in = True
                    st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")


def new_project():
    with st.form("new_project"):
        username = st.text_input("Username", value="mlox")
        password = st.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        configs = load_all_server_configs("./stacks")
        config = st.selectbox(
            "System Configuration",
            configs,
            format_func=lambda x: f"{x.name} {x.version} - {x.description_short}",
            help="Please select the configuration that matches your server.",
        )
        params = dict()
        infra = Infrastructure()
        setup_func = config.instantiate_ui("setup")
        if setup_func:
            params = setup_func(infra)
        if st.form_submit_button("Submit", type="primary"):
            bundle = infra.add_server(config, params)
            if not bundle:
                st.error(
                    "Something went wrong. Check server credentials and try again."
                )
            else:
                with st.spinner("Initializing server, writing keyfile, etc..."):
                    bundle.server.setup()
                    server_dict = dataclass_to_dict(bundle.server)
                    save_to_json(server_dict, f"./{username}.key", password, True)

            ms = None
            try:
                ms = MloxSession(username, password)
                if ms.secrets.is_working():
                    ms.infra = infra
                    config = load_config("./stacks", "/tsm", "mlox.tsm.yaml")
                    ms.infra.add_service(bundle.server.ip, config, {})
                    ms.infra.get_service(TSMService.__class__.__name__).pw = password
                    print(ms.infra.get_service(TSMService.__class__.__name__).pw)
                    bundle.tags.append("mlox-secrets")
                    ms.save_infrastructure()
                    st.session_state["mlox"] = ms
                    st.session_state.is_logged_in = True
                    st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")


if not st.session_state.get("is_logged_in", False):
    tab_login, tab_new = st.tabs(["Existing Project", "New Project"])

    with tab_login:
        login()

    with tab_new:
        new_project()

else:
    if st.button("Log out"):
        st.session_state.is_logged_in = False
        st.session_state.pop("mlox")
        st.rerun()
