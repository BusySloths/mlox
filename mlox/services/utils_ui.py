import streamlit as st


def save_infrastructure():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()
