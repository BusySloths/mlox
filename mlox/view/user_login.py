import os
import streamlit as st

from mlox.session import MloxSession

st.write("# User Login/Logout")


if not st.session_state.get("is_logged_in", False):
    with st.form("login"):
        username = st.text_input("Username", value="mlox")
        password = st.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        submitted = st.form_submit_button("Log in")
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
            st.error(f"Login failed")
else:
    if st.button("Log out"):
        st.session_state.is_logged_in = False
        st.session_state.pop("mlox")
        st.rerun()
