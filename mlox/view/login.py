import os
import streamlit as st

from mlox.session import MloxSession
from mlox.infra import Infrastructure
from mlox.utils import dataclass_to_dict, save_to_json
from mlox.view.utils import form_add_server


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
        ip, port, root, pw, config = form_add_server()
        submitted = st.form_submit_button("New")
        if submitted:
            bundle = Infrastructure().add_server(
                config,
                {
                    "${MLOX_IP}": ip,
                    "${MLOX_PORT}": str(port),
                    "${MLOX_ROOT}": root,
                    "${MLOX_ROOT_PW}": pw,
                },
            )
            if not bundle:
                st.error(
                    "Something went wrong. Check server credentials and try again."
                )
            else:
                with st.spinner("Initializing server, writing keyfile, etc..."):
                    bundle.initialize()  # initialize server (add mlox user, ssh keys, update etc)
                    server_dict = dataclass_to_dict(bundle.server)
                    save_to_json(server_dict, f"./{username}.key", password, True)

            ms = None
            try:
                ms = MloxSession(username, password)
                if ms.secrets.is_working():
                    ms.infra.bundles.append(bundle)
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
