import os
import json
import platform
import logging
import streamlit as st

from importlib import metadata as importlib_metadata  # py3.8+

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


def project_settings_and_logout():
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
        st.page_link(
            "view/services.py",
            use_container_width=True,
            label="Open Services",
            icon=":material/linked_services:",
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
        # --- Actions ---
        a1, a2 = st.columns([1, 1])
        with a1:
            if st.button("Reload Configs", icon=":material/refresh:"):
                try:
                    infra.populate_configs()
                    st.success("Configs reloaded.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to reload configs: {e}")

        # --- Helper to mask sensitive env values ---
        def _mask(val: str | None, keep: int = 2) -> str:
            if not val:
                return ""
            if len(val) <= keep * 2:
                return "*" * len(val)
            return f"{val[:keep]}***{val[-keep:]}"

        # --- Runtime info ---
        try:
            pkg_ver = importlib_metadata.version("busysloths-mlox")
        except Exception:
            pkg_ver = "(editable / unknown)"
        py_ver = platform.python_version()
        os_name = platform.system()
        os_ver = platform.release()

        st.markdown("#### Runtime")
        r1, r2, r3 = st.columns(3)
        r1.metric("MLOX package", pkg_ver)
        r2.metric("Python", py_ver)
        r3.metric("OS", f"{os_name} {os_ver}")

        # --- Secret manager details ---
        sm = getattr(session, "secrets", None)
        sm_cls = sm.__class__.__name__ if sm else "(none)"
        sm_ok = sm.is_working() if sm else False
        st.markdown("#### Secret Manager")
        s1, s2, s3 = st.columns(3)
        s1.metric("Backend", sm_cls)
        s2.metric("Working", "Yes" if sm_ok else "No")
        try:
            sm_keys = len(sm.list_secrets(keys_only=True)) if sm else 0
        except Exception:
            sm_keys = 0
        s3.metric("Secrets", sm_keys)

        # --- Environment (safe subset) ---
        st.markdown("#### Environment (selected)")
        env_keys = [
            "MLOX_CONFIG_USER",
            "MLOX_CONFIG_PASSWORD",
            "MLOX_PROJECT",
            "MLOX_PASSWORD",
        ]
        ecols = st.columns(len(env_keys))
        for i, k in enumerate(env_keys):
            v = os.environ.get(k)
            ecols[i].metric(k, _mask(v))

        # --- Infrastructure breakdown ---
        st.markdown("#### Infrastructure Overview")
        for bundle in infra.bundles:
            with st.container(border=True):
                st.markdown(
                    f"**Server:** `{bundle.server.ip}` • Backend: `{bundle.server.backend}` • State: `{bundle.server.state}`"
                )
                if bundle.services:
                    for svc in bundle.services:
                        try:
                            cfg = infra.get_service_config(svc)
                            cfg_name = cfg.name if cfg else svc.__class__.__name__
                        except Exception:
                            cfg_name = svc.__class__.__name__
                        ports = ", ".join(
                            f"{k}:{v}"
                            for k, v in getattr(svc, "service_ports", {}).items()
                        )
                        st.markdown(
                            f"- {cfg_name} (`{svc.name}`) • state: `{getattr(svc, 'state', '?')}`"
                            + (f" • ports: {ports}" if ports else "")
                        )
                else:
                    st.caption("No services on this server yet.")

        # --- Downloadable debug snapshot ---
        debug = {
            "mlox_version": pkg_ver,
            "python": py_ver,
            "os": f"{os_name} {os_ver}",
            "project": {
                "name": session.project.name,
                "version": getattr(session.project, "version", ""),
                "created_at": session.project.created_at,
                "last_opened_at": session.project.last_opened_at,
                "secret_manager_class": session.project.secret_manager_class,
            },
            "secret_manager": {
                "class": sm_cls,
                "working": sm_ok,
                "secrets_count": sm_keys,
            },
            "infrastructure": [
                {
                    "server": {
                        "ip": b.server.ip,
                        "backend": b.server.backend,
                        "state": b.server.state,
                    },
                    "services": [
                        {
                            "name": s.name,
                            "class": s.__class__.__name__,
                            "state": getattr(s, "state", ""),
                            "ports": getattr(s, "service_ports", {}),
                        }
                        for s in b.services
                    ],
                }
                for b in infra.bundles
            ],
            "env": {k: _mask(os.environ.get(k)) for k in env_keys},
        }
        st.download_button(
            "Download Debug Snapshot",
            data=json.dumps(debug, indent=2).encode("utf-8"),
            file_name=f"mlox_debug_{session.project.name}.json",
            mime="application/json",
            use_container_width=True,
        )


if not st.session_state.get("is_logged_in", False):
    tab_login, tab_new = st.tabs(["Load Existing Project", "Create a New Project"])

    with tab_login:
        login()

    with tab_new:
        new_project()
else:
    project_settings_and_logout()
