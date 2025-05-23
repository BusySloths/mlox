import streamlit as st


from mlox.services.airflow.docker import AirflowDockerService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: AirflowDockerService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")

    c1, c2, c3 = st.columns([70, 12, 18])
    repo = c1.selectbox(
        "Add repository",
        bundle.repos,
        format_func=lambda repo: repo.name,
        label_visibility="collapsed",
    )
    if c2.button("Add to DAGs"):
        st.info("Adding to DAGs")
        with bundle.server.get_server_connection() as conn:
            service.add_repo(conn, repo)
    if c3.button("Remove from DAGs"):
        st.info("Removing from DAGs")
        with bundle.server.get_server_connection() as conn:
            service.remove_repo(conn, repo)

    st.write(repo)
