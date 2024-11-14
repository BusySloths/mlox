import streamlit as st

from mlox.configs import services

st.set_page_config(page_title="MOPS", page_icon="👋")

st.write("# Welcome to MOPS! 👋")

st.sidebar.success("Select a demo above.")

st.markdown(
    """
    MOPS main
    """
)

if services is not None:
    key = st.selectbox("Services", list(services.keys()))
    st.link_button("Link", services[key].get_service_url())
    st.write(services[key])
