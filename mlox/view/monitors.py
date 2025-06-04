import pandas as pd

import streamlit as st


def monitors():
    st.markdown("""
    # Monitor
    This is where you can monitor your infrastructure.
    """)
    ms = st.session_state.mlox
    infra = ms.infra

    monitor = st.selectbox(
        "Select Monitor",
        infra.list_monitors(),
        format_func=lambda x: f"{x.service.name} @ {x.service.service_url}",
    )

    bundle = infra.get_bundle_by_service(monitor.service)
    callable_settings = monitor.config.instantiate_ui("settings")
    if callable_settings and bundle:
        callable_settings(infra, bundle, monitor.service)


monitors()
