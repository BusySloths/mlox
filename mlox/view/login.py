import os
import streamlit as st

from mlox.session import MloxSession
from mlox.infra import Infrastructure
from mlox.view.utils import plot_config_nicely
from mlox.config import load_all_server_configs


def create_session(username, password) -> bool:
    ms = None
    try:
        print(f"Creating session for user: {username}")
        ms = MloxSession(username, password)
        print(f"Done Creating session for user: {username}")
        if not ms.secrets or ms.secrets.is_working():
            st.session_state["mlox"] = ms
            st.session_state.is_logged_in = True
    except Exception as e:
        print(e)
        return False
    return True


def login():
    with st.form("Open Project"):
        username = st.text_input(
            "Project Name", value=os.environ.get("MLOX_CONFIG_USER", "mlox")
        )
        password = st.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        submitted = st.form_submit_button("Open Project", icon=":material/login:")
        if submitted:
            if create_session(username, password):
                st.success("Project opened successfully!")
                st.rerun()
            else:
                st.error(
                    "Failed to open project. Check username and password.",
                    icon=":material/error:",
                )


def new_project():
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        username = c1.text_input("Project Name", value="mlox")
        password = c2.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        configs = load_all_server_configs()
        config = c3.selectbox(
            "System Configuration",
            configs,
            format_func=lambda x: f"{x.name} {x.version} - {x.description_short}",
            help="Please select the configuration that matches your server.",
        )
        params = dict()
        infra = Infrastructure()
        setup_func = config.instantiate_ui("setup")
        plot_config_nicely(config)
        if setup_func:
            params = setup_func(infra, config)
        if st.button("Setup Project", icon=":material/computer:", type="primary"):
            ms = MloxSession.new_infrastructure(
                infra, config, params, username, password
            )
            if not ms:
                st.error(
                    "Something went wrong. Check server credentials and try again."
                )
                return
            st.session_state["mlox"] = ms
            st.session_state.is_logged_in = True
            st.success("Project created successfully!")
            st.rerun()


def logout():
    session = st.session_state.get("mlox")
    infra = session.infra
    st.markdown(f"# Project: {session.username}")
    st.markdown("---")
    st.markdown("## Infrastructure")
    st.markdown(
        f"Your infrastrcuture consists of **`{len(infra.bundles)}` servers and `{sum([len(b.services) for b in infra.bundles])}` services.**"
    )

    st.markdown("## Danger Zone")
    st.warning(
        "Closing the project will log you out and remove the current session from memory. "
    )

    if st.button("Close Project", icon=":material/logout:"):
        st.session_state.is_logged_in = False
        st.session_state.pop("mlox")
        st.rerun()
    with st.expander("Admin"):
        if st.button("Reload Configs", icon=":material/refresh:"):
            infra.populate_configs()
            st.rerun()


if not st.session_state.get("is_logged_in", False):
    tab_login, tab_new = st.tabs(["Load Existing Project", "Create a New Project"])

    with tab_login:
        login()

    with tab_new:
        new_project()
else:
    logout()
