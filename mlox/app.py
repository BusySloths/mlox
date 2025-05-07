import streamlit as st


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


def services():
    st.markdown("""
    # Services
    This is where you can manage your services.""")


def service_airflow():
    st.markdown("""
    # Service Airflow
    This is where you can manage your Airflow service.""")


def repos():
    st.markdown("""
    # Repositories
    This is where you can manage your repositories.""")


def monitor():
    st.markdown("""
    # Monitor
    This is where you can monitor your infrastructure.

    ## System Health
    - CPU Usage
    - Memory Usage
    - Disk Usage
    - Network Traffic
    ## Service Health
    - Service Status
    - Error Logs
    - Performance Metrics
    ## OTEL Metrics
    - Service Metrics
    - Service Traces
    - Service Logs
    ## Active Data Surveillance (* later)
    - Model Performance 
    - Data Drift
    ## Performance Metrics (* later)
    - Service Performance
    - System Performance
    ## Alerts and Notifications (* later)
    - Alert Configuration
    - Notification Channels
    - Alert History
    """)


def secrets():
    st.markdown("""
    # Outputs
    This is the collections of all the outputs of your MLOps stack to be used in your applications.:
    - Keys and secrets
    - Configurations
    """)

    ip = "<IP_ADDRESS>"
    st.selectbox(
        "Choose Secret Manager Backend",
        [
            "Local (not recommended)",
            f"OpenBAO on {ip}",
        ],
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


pages_admin = [
    st.Page(
        "view/admin_user.py", title="User Management", icon=":material/manage_accounts:"
    ),
]


pages_logged_out = {
    "": [st.Page(welcome, title="Home", icon=":material/home:")],
    "Your Account": [
        st.Page("view/user_login.py", title="Login", icon=":material/login:"),
    ],
}

pages_logged_in = {
    "": [st.Page(welcome, title="Home", icon=":material/home:")],
    "Your account": [
        st.Page("view/user_login.py", title="Logout", icon=":material/logout:"),
        st.Page(
            "view/user_profile.py", title="Profile", icon=":material/account_circle:"
        ),
    ],
    "Your Infrastructure": [
        st.Page(news, title="Security and News", icon=":material/news:"),
        st.Page(
            "view/manage.py",
            title="Infrastructure",
            icon=":material/network_node:",
        ),
        st.Page(
            services,
            title="Services",
            icon=":material/linked_services:",
        ),
        st.Page(
            repos,
            title="Repositories",
            icon=":material/database:",
        ),
        st.Page(
            secrets,
            title="Secret Management",
            icon=":material/key:",
        ),
        st.Page(
            monitor,
            title="Monitor",
            icon=":material/monitor:",
        ),
    ],
    "Help and Documentation": [
        st.Page(
            help,
            title="Documentation",
            icon=":material/docs:",
        ),
    ],
}


if st.session_state.get("is_admin", False):
    pages_logged_in["Admin"] = pages_admin

pages = pages_logged_out
if st.session_state.get("is_logged_in", False):
    pages = pages_logged_in

pg = st.navigation(pages)

pg.run()
