import streamlit as st

from mlox.session import MloxSession


def show_service_logs_ui(session: MloxSession, service_name: str):
    """Simple Streamlit widget to show logs for a service.

    Example usage from the main app:
        from mlox.view.logs import show_service_logs_ui
        show_service_logs_ui(session, 'my-service')
    """
    # st.header(f"Logs for {service_name}")

    svc = session.infra.get_service(service_name)
    if not svc:
        st.error("Service not found in infrastructure")
        return

    bundle = session.infra.get_bundle_by_service(svc)
    if not bundle:
        st.error("Could not find server bundle for this service")
        return

    conn_ctx = bundle.server.get_server_connection()
    with conn_ctx as conn:
        labels = list(svc.compose_service_names.keys())
        if not labels:
            st.info("No compose service labels configured for this service")
            return

        c1, c2, c3 = st.columns(3, width="stretch", vertical_alignment="bottom")
        label = c1.selectbox("Compose service label", labels)
        tail = c2.number_input(
            "Lines", min_value=50, max_value=2000, value=200, step=50
        )
        if c3.button("Refresh"):
            logs = svc.compose_service_log_tail(conn, label=label, tail=tail)
            st.text_area("Logs", value=logs, height=600, disabled=True)
