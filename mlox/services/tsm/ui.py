import streamlit as st


from mlox.services.tsm.service import TSMService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: TSMService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")
    st.write(f'Password: "{service.pw}"')

    tsm = service.get_secret_manager(bundle)
    st.write(tsm.list_secrets())

    secret_name = st.text_input("Secret Name", key="secret_name")
    secret_value = st.text_input("Secret Value", key="secret_value")
    if st.button("Save Secret"):
        tsm.save_secret(secret_name, secret_value)
        st.rerun()
