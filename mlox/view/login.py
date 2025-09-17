import os
import logging
import streamlit as st

from mlox.session import MloxSession

logger = logging.getLogger(__name__)


def create_session(project_name, password, create_new_project: bool) -> bool:
    if not create_new_project:
        if not MloxSession.check_project_exists_and_loads(project_name, password):
            logger.warning(
                f"Project {project_name} does not exist or cannot be loaded."
            )
            return False
    ms = None
    try:
        print(f"Creating session for project: {project_name}")
        ms = MloxSession(project_name, password)
        st.session_state["mlox"] = ms
        st.session_state.is_logged_in = True
        print(f"Done Creating session for project: {project_name}")
    except Exception as e:
        logger.error(f"Error creating session for project {project_name}: {e}")
        return False
    return True


def login():
    with st.form("Open Project"):
        project_name = st.text_input(
            "Project Name", value=os.environ.get("MLOX_CONFIG_USER", "mlox")
        )
        password = st.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        submitted = st.form_submit_button("Open Project", icon=":material/login:")
        if submitted:
            if create_session(project_name, password, create_new_project=False):
                st.success("Project opened successfully!")
                st.rerun()
            else:
                st.error(
                    "Failed to open project. Check project name and password.",
                    icon=":material/error:",
                )


def new_project():
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        project_name = c1.text_input("Project Name", value="mlox")
        password = c2.text_input(
            "Password",
            value=os.environ.get("MLOX_CONFIG_PASSWORD", ""),
            type="password",
        )
        if c3.button("Create Project", icon=":material/add_circle:"):
            if create_session(project_name, password, create_new_project=True):
                st.success("Project created successfully!")
                st.rerun()
            else:
                st.error(
                    "Failed to create project. Check project name and password.",
                    icon=":material/error:",
                )


def logout():
    session = st.session_state.get("mlox")
    if not session:
        st.error("No active project session found. Please open a project first.")
        return

    infra = session.infra

    # Header
    st.markdown(f"# 🗂️ Project: {session.project.name}")
    cols = st.columns([2, 1])
    with cols[0]:
        st.caption(
            f"Created: {session.project.created_at.split('.')[0].replace('T', ' ')}"
        )
        st.caption(
            f"Last opened: {session.project.last_opened_at.split('.')[0].replace('T', ' ')}"
        )
    with cols[1]:
        sm_name = (
            session.secrets.__class__.__name__
            if getattr(session, "secrets", None)
            else "(none)"
        )
        st.metric(label="Secret Manager", value=sm_name)

    st.markdown("---")

    # Infrastructure summary cards
    server_count = len(infra.bundles) if infra and hasattr(infra, "bundles") else 0
    service_count = (
        sum(len(b.services) for b in infra.bundles)
        if infra and hasattr(infra, "bundles")
        else 0
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Servers", f"{server_count}")
    c2.metric("Services", f"{service_count}")
    # small helper column with quick actions
    with c3.container(border=True):
        st.page_link(
            "view/infrastructure.py",
            use_container_width=True,
            label="Open Infrastructure",
            icon=":material/computer:",
        )

    st.markdown("---")

    # Danger zone with clear CTA
    st.markdown("## ❗ Danger Zone")
    st.warning(
        "Closing the project will remove the current session from memory and you will be logged out."
    )

    col_confirm, col_cancel = st.columns([1, 1])
    with col_confirm:
        if st.button(
            "Close Project",
            key="close_project",
            help="Close and remove the current project session",
            use_container_width=True,
        ):
            st.session_state.is_logged_in = False
            st.session_state.pop("mlox", None)
            st.success("Project closed.")
            st.rerun()
    with col_cancel:
        if st.button("Cancel", key="cancel_close", use_container_width=True):
            st.info("Close cancelled.")

    # Admin section
    with st.expander("Admin - Configs & Debug"):
        if st.button("Reload Configs", icon=":material/refresh:"):
            try:
                infra.populate_configs()
                st.success("Configs reloaded.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to reload configs: {e}")


if not st.session_state.get("is_logged_in", False):
    tab_login, tab_new = st.tabs(["Load Existing Project", "Create a New Project"])

    with tab_login:
        login()

    with tab_new:
        new_project()
else:
    logout()
