import streamlit as st


from mlox.services.k8s_dashboard.k8s import K8sDashboardService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: K8sDashboardService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")
