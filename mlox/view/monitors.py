import pandas as pd
import streamlit as st

from typing import cast

from mlox.infra import Infrastructure


def save_infra():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


def manage_monitors():
    st.markdown("""
    # Monitor
    This is where you can monitor your infrastructure.
    """)
    infra = None
    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    my_monitors = []
    for m in infra.filter_by_group("monitor"):
        bundle = infra.get_bundle_by_service(m)
        if not bundle:
            continue
        my_monitors.append(
            {
                "ip": bundle.server.ip,
                "server": bundle.name,
                "name": m.name,
                "state": m.state,
                "bundle": bundle,
                "service": m,
            }
        )

    df = pd.DataFrame(
        my_monitors,
        columns=["ip", "server", "name", "state", "bundle", "service"],
    )
    selection = st.dataframe(
        df[["server", "name", "state"]],
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        bundle = my_monitors[idx]["bundle"]
        monitor = my_monitors[idx]["service"]

        config = infra.get_service_config(monitor)

        callable_settings_func = config.instantiate_ui("settings")
        if callable_settings_func and monitor.state == "running":
            callable_settings_func(infra, bundle, monitor)

        # if st.button("Delete"):
        #     with st.spinner(f"Deleting {name}..."):
        #         infra.teardown_service(monitor)
        #     save_infra()
        #     st.rerun()


manage_monitors()
