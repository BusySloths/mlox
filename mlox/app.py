import streamlit as st

from typing import cast

from mlox.infra import Infrastructure


def news():
    st.markdown("""
    # News and Security
    This is where you can find the latest news and security updates.
    """)


def help():
    st.markdown("""
    # Help and Documentation
    Quick access to the documentation and help resources.
    """)
    ms = st.session_state["mlox"]
    infra = ms.infra
    for b in infra.bundles:
        for s in b.services:
            config = infra.get_service_config(s)
            st.markdown(
                f"__{config.name}__ docs: [{config.links['documentation']}]({config.links['documentation']})"
            )


def welcome():
    st.image("resources/mlox_logo_wide.png")
    st.markdown("""
    # Welcome to MLOX – MLOps Infrastructure Made Simple
    
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
    st.session_state["sidebar_menu"] = st.checkbox(
        "Sidebar Menu",
        value=True,
        key="my_sidebar_menu",
        help="Toggle the sidebar menu visibility.",
    )


st.set_page_config(
    page_title="MLOX Infrastructure Management",
    page_icon="resources/mlox_logo_small.png",
    layout="wide",
)

st.logo(
    "resources/mlox.png",
    size="large",
    icon_image="resources/mlox_logo_small.png",
)


pages_logged_out = {
    "": [
        st.Page(welcome, title="Home", icon=":material/home:"),
        st.Page("view/login.py", title="Login", icon=":material/login:"),
    ],
}

pages_logged_in = {
    "": [
        st.Page(welcome, title="Home", icon=":material/home:"),
        st.Page("view/login.py", title="Logout", icon=":material/logout:"),
    ],
}

pages_infrastructure = [
    st.Page(news, title="Security and News", icon=":material/news:"),
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
        st.Page(
            help,
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


if st.session_state.get("sidebar_menu", True):
    pg = st.navigation(pages, position="sidebar")
else:
    pg = st.navigation(pages, position="top")

pg.run()
