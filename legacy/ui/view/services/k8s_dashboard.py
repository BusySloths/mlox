import streamlit as st


from mlox.services.k8s_dashboard.k8s import K8sDashboardService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: K8sDashboardService):
    # st.markdown(f"Settings for service {service.name}")

    token = service.get_login_token(bundle)
    # st.write(f"Login Token: _`{token}`_")
    st.text_area("Login Token", token)
    st.link_button("Dashboard Link", service.service_urls["Kubernetes Dashboard"])
