import streamlit as st


from mlox.services.kubeapps.k8s import KubeAppsService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: KubeAppsService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")

    # with bundle.server.get_server_connection() as conn:
    #     res = service.check(conn)
    #     st.write(res)
