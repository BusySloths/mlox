import streamlit as st


st.write("# User Login/Logout")


if not st.session_state.get("is_logged_in", False):
    if st.button("Log in"):
        st.session_state.is_logged_in = True
        st.rerun()
else:
    if st.button("Log out"):
        st.session_state.is_logged_in = False
        st.rerun()
