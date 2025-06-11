import streamlit as st


from mlox.services.airflow.docker import AirflowDockerService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: AirflowDockerService):
    st.header(f"Settings for service {service.name}")
    st.write(f"IP: {bundle.server.ip}")
    st.write(f"UI User: {service.ui_user}")
    st.write(f'UI Password: "{service.ui_pw}"')

    # list associated repositories
    st.markdown("## Associated repositories")
    for repo in bundle.repos:
        if repo.path.startswith(service.path_dags):
            st.markdown(
                f"- **{repo.name}**: [{repo.link}]({repo.link}) - Path: `{repo.path}`"
            )

    # add a repository to the DAGs
    st.markdown(
        "## Add or remove repositories from DAGs\n"
        "You can add or remove repositories from the DAGs folder. "
        "This will allow you to manage your Airflow DAGs more easily."
    )
    c1, c2, c3 = st.columns([70, 12, 18])
    repo = c1.selectbox(
        "Add repository",
        [repo for repo in bundle.repos if not repo.path.startswith(service.path_dags)],
        format_func=lambda repo: f"{repo.name} [{repo.path}]",
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
    # st.write(repo)
