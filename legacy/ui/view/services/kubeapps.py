import streamlit as st


from mlox.services.kubeapps.k8s import KubeAppsService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: KubeAppsService):
    token = service.get_login_token(bundle)
    st.text_area("Login Token", token)
    st.link_button("KubeApps Link", service.service_urls["KubeApps"])
