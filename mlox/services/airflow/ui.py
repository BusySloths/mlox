import streamlit as st


from mlox.services.airflow.docker import AirflowDockerService
from mlox.infra import Infrastructure, Bundle, Repo


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
        if not repo.path.startswith(service.path_dags):
            infra.create_and_add_repo(bundle.server.ip, repo.link, service.path_dags)
        else:
            st.info("Repository already in DAGs")

    if c3.button("Remove from DAGs"):
        st.info("Removing from DAGs")
        if repo.path.startswith(service.path_dags):
            infra.remove_repo(bundle.server.ip, repo)
        else:
            st.info("Repository not found in DAGs")
    st.write(repo)
