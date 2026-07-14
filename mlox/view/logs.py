import streamlit as st

from mlox.project import ProjectWorkspace


def _service_log_labels(service) -> list[str]:
    labels = getattr(service, "log_labels", None)
    if callable(labels):
        return list(labels())
    return list((getattr(service, "compose_service_names", {}) or {}).keys())


def _service_log_tail(service, conn, *, label: str, tail: int) -> str:
    log_tail = getattr(service, "service_log_tail", None)
    if callable(log_tail):
        return log_tail(conn, label=label, tail=tail)
    return service.compose_service_log_tail(conn, label=label, tail=tail)


def show_service_logs_ui(application: ProjectWorkspace, service_name: str):
    """Simple Streamlit widget to show logs for a service.

    Example usage from the main app:
        from mlox.view.logs import show_service_logs_ui
        show_service_logs_ui(session, 'my-service')
    """
    # st.header(f"Logs for {service_name}")

    infra = application.infrastructure
    svc = infra.get_service(service_name)
    if not svc:
        st.error("Service not found in infrastructure")
        return

    bundle = infra.get_bundle_by_service(svc)
    if not bundle:
        st.error("Could not find server bundle for this service")
        return

    conn_ctx = bundle.server.get_server_connection()
    with conn_ctx as conn:
        labels = _service_log_labels(svc)
        if not labels:
            st.info("No log labels configured for this service")
            return

        c1, c2, c3 = st.columns(3, width="stretch", vertical_alignment="bottom")
        label = c1.selectbox("Log label", labels)
        tail = c2.number_input(
            "Lines", min_value=50, max_value=2000, value=200, step=50
        )
        if c3.button("Refresh"):
            logs = _service_log_tail(svc, conn, label=label, tail=tail)
            st.text_area("Logs", value=logs, height=600, disabled=True)
