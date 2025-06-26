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
        infra.filter_by_group("monitor"),
        format_func=lambda x: f"{x.name} @ {x.service_url}",
    )

    if monitor:
        bundle = infra.get_bundle_by_service(monitor)
        config = infra.get_service_config(monitor)
        if config:
            callable_settings = config.instantiate_ui("settings")
            if callable_settings and bundle:
                callable_settings(infra, bundle, monitor)


monitors()
