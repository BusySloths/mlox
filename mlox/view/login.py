import os
import streamlit as st

from mlox.session import MloxSession
from mlox.infra import Infrastructure
from mlox.view.utils import plot_config_nicely
from mlox.config import load_all_server_configs


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
            ms = None
            try:
                ms = MloxSession(username, password)
                if ms.secrets.is_working():
                    st.session_state["mlox"] = ms
                    st.session_state.is_logged_in = True
                    st.rerun()
            except Exception as e:
                st.error(f"Open project failed: {e}")


def new_project():
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        username = c1.text_input("Project Name", value="mlox")
        password = c2.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        configs = load_all_server_configs("./stacks")
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

            # bundle = infra.add_server(config, params)
            # if not bundle:
            #     st.error(
            #         "Something went wrong. Check server credentials and try again."
            #     )
            # else:
            #     ms = None
            #     with st.spinner(
            #         "Initializing server, writing keyfile, etc...", show_time=True
            #     ):
            #         try:
            #             bundle.server.setup()
            #         except Exception as e:
            #             if not (bundle.server.mlox_user and bundle.server.remote_user):
            #                 st.error(f"Server setup failed: {e}")
            #                 return
            #         try:
            #             server_dict = dataclass_to_dict(bundle.server)
            #             save_to_json(server_dict, f"./{username}.key", password, True)
            #         except Exception as e:
            #             st.error(f"Generating key file failed: {e}")
            #             return
            #         ms = MloxSession(
            #             username, password
            #         )  # creates empty infrastructure instance
            #         if ms.secrets.is_working():
            #             try:
            #                 ms.infra = infra
            #                 config = load_config("./stacks", "/tsm", "mlox.tsm.yaml")
            #                 bundle = ms.infra.add_service(bundle.server.ip, config, {})
            #                 bundle.services[0].pw = password
            #                 bundle.tags.append("mlox.secrets")
            #                 bundle.tags.append("mlox.primary")
            #                 ms.save_infrastructure()
            #                 st.session_state["mlox"] = ms
            #                 st.session_state.is_logged_in = True
            #                 st.rerun()
            #             except Exception as e:
            #                 st.error(f"Infrastructure setup failed: {e}")
            #                 print(e)

            #         else:
            #             st.error("Secret manager setup failed.")


if not st.session_state.get("is_logged_in", False):
    tab_login, tab_new = st.tabs(["Load Existing Project", "Create a New Project"])

    with tab_login:
        login()

    with tab_new:
        new_project()

else:
    if st.button("Close Project", icon=":material/logout:"):
        st.session_state.is_logged_in = False
        st.session_state.pop("mlox")
        st.rerun()
