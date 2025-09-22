import os
import streamlit as st

from typing import cast

from mlox.infra import Infrastructure
from mlox.session import MloxSession

# --- Path setup ---
# Get the absolute path to the directory containing this script (app.py)
# This makes the app robust to being run from any CWD.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCES_DIR = os.path.join(APP_DIR, "resources")


def get_resource_path(filename: str) -> str:
    """Constructs an absolute path to a resource file."""
    return os.path.join(RESOURCES_DIR, filename)


def auto_login():
    if not st.session_state.get("is_logged_in", False):
        prj = os.environ.get("MLOX_PROJECT", None)
        pw = os.environ.get("MLOX_PASSWORD", None)
        if prj and pw:
            try:
                ms = MloxSession(prj, pw)
                st.session_state["mlox"] = ms
                st.session_state.is_logged_in = True
            except Exception:
                return
    return


def news():
    st.markdown("""
    # News and Security
    This is where you can find the latest news and security updates.
    """)


def welcome():
    # Header with logo + tagline
    c1, c2 = st.columns([1, 2], vertical_alignment="center")
    with c1:
        st.image(get_resource_path("mlox_logo_wide.png"))
    with c2:
        st.markdown("## Calm MLOps, at a sloth’s pace 🦥")
        st.markdown(
            "Deploy, monitor, and maintain production‑ready MLOps — without rushing."
        )

    # Quick overview points
    st.markdown("---")
    st.markdown("#### What you can do here")
    c3, c4, c5 = st.columns(3)
    with c3:
        st.markdown("- Install services like MLflow, Airflow, Redis")
        st.markdown("- Import public/private GitHub repos")
    with c4:
        st.markdown("- Manage servers and Kubernetes clusters")
        st.markdown("- Centralize secrets and configuration")
    with c5:
        st.markdown("- Monitor metrics, logs, and traces")
        st.markdown("- Use friendly APIs in your apps")

    # Project snapshot (if logged in)
    if "mlox" in st.session_state:
        try:
            infra = cast(Infrastructure, st.session_state.mlox.infra)
            bundles = infra.bundles
            server_count = len(bundles)
            service_count = sum(len(b.services) for b in bundles)
            st.markdown("---")
            st.markdown("#### Project snapshot")
            m1, m2 = st.columns(2)
            m1.metric("Servers", server_count)
            m2.metric("Services", service_count)
        except Exception:
            pass

    # Helpful next steps
    st.markdown("---")
    st.markdown("#### Get started")
    st.markdown(
        "- Use the sidebar to open Infrastructure, Services, and Docs.\n"
        "- Not logged in yet? Open ‘Open Project’ to connect.\n"
        "- Prefer reading first? Explore the docs and repo below."
    )

    # External links
    l1, l2, l3 = st.columns(3)
    with l1:
        st.link_button("Project Site", "https://mlox.org", use_container_width=True)
    with l2:
        st.link_button(
            "Documentation",
            "https://github.com/BusySloths/mlox#readme",
            use_container_width=True,
        )
    with l3:
        st.link_button(
            "GitHub", "https://github.com/BusySloths/mlox", use_container_width=True
        )


st.set_page_config(
    page_title="MLOX Infrastructure Management",
    page_icon=get_resource_path("mlox_logo_small.png"),
    layout="wide",
)

st.logo(
    get_resource_path("mlox.png"),
    size="large",
    icon_image=get_resource_path("mlox_logo_small.png"),
)

auto_login()

if "mlox" in st.session_state:
    session = st.session_state.mlox
    if not session.secrets or not session.secrets.is_working():
        st.warning(
            "Project does not have an active secret manager configured "
            "meaning changes to infrastructure or services will not be saved. "
            "To resolve this issue, please follow these steps: \n"
            " - Add at least one server to your infrastructure\n"
            " - Set up a secret manager service (first secret manager will be used automatically)\n",
            icon=":material/warning:",
        )


pages_logged_out = {
    "": [
        st.Page(welcome, title="Home", icon=":material/home:"),
        st.Page("view/login.py", title="Open Project", icon=":material/login:"),
    ],
}

pages_logged_in = {
    "": [
        st.Page(welcome, title="Home", icon=":material/home:"),
    ],
}

pages_infrastructure = [
    st.Page("view/login.py", title="Settings", icon=":material/settings:"),
    st.Page(
        "view/infrastructure.py",
        title="Infrastructure",
        icon=":material/network_node:",
    ),
    st.Page(
        "view/services.py",
        title="Services",
        icon=":material/linked_services:",
    ),
]

if st.session_state.get("mlox", None):
    infra = cast(Infrastructure, st.session_state.mlox.infra)

    if len(infra.filter_by_group("repository")) > 0:
        pages_infrastructure.append(
            st.Page(
                "view/repositories.py",
                title="Repositories",
                icon=":material/database:",
            )
        )

    pages_infrastructure.append(
        st.Page(
            "view/secret_manager.py",
            title="Secret Management",
            icon=":material/key:",
        )
    )

    if len(infra.filter_by_group("model-server")) > 0:
        pages_infrastructure.append(
            st.Page(
                "view/models.py",
                title="Models",
                icon=":material/model_training:",
            )
        )
    if len(infra.filter_by_group("monitor")) > 0:
        pages_infrastructure.append(
            st.Page(
                "view/monitors.py",
                title="Monitor",
                icon=":material/monitor:",
            )
        )


pages_docs = {
    "Help and Documentation": [
        st.Page(news, title="Security and News", icon=":material/news:"),
        st.Page(
            "view/docs.py",
            title="Documentation",
            icon=":material/docs:",
        ),
    ],
}

pages = pages_logged_out
if st.session_state.get("is_logged_in", False):
    pages = pages_logged_in
    prj_name = st.session_state["mlox"].project.name
    pages[prj_name] = pages_infrastructure
    pages.update(pages_docs)


pg = st.navigation(pages, position="sidebar")
pg.run()
