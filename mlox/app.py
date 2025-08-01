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
                if ms.secrets.is_working():
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
    st.markdown("# BusySloths presents")
    st.image(get_resource_path("mlox_logo_wide.png"))
    st.markdown("""
    ### Accelerate your ML journey—deploy production-ready MLOps in minutes, not months.

    
    MLOX helps individuals and small teams deploy, configure, and monitor full MLOps stacks with minimal effort. 
    Through this interface, you can:
    - Install MLOps tools like MLFlow, Airflow, and Feast with one click
    - Customize infrastructure using simple forms
    - Monitor your metrics, logs, and traces in one place
    - Secure deployments via built-in user management and secret handling
    - Easily integrate your applications using a simple API
    - Everything runs on your servers or hybrid setups fully open-source, fully yours.    
                
    ### Get Started

    Explore the different sections of the application in the menu on the left.
    If you are not already logged in, you can do so under "Your Account".
    """)


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
    prj_name = st.session_state["mlox"].username
    pages[prj_name] = pages_infrastructure
    pages.update(pages_docs)


pg = st.navigation(pages, position="sidebar")
pg.run()
