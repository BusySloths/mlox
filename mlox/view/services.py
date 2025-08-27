import pandas as pd
import streamlit as st

from typing import cast

from mlox.infra import Infrastructure
from mlox.config import load_all_service_configs
from mlox.view.utils import plot_config_nicely, st_hack_align


def save_infra():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


def installed_services():
    st.markdown("""
    This is where you can manage your services.""")
    infra = None
    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    services = []
    for bundle in infra.bundles:
        for s in bundle.services:
            services.append(
                {
                    "ip": bundle.server.ip,
                    "name": s.name,
                    "version": infra.get_service_config(s).version,
                    "links": [f"{k}:{v}" for k, v in s.service_urls.items()],
                    "state": s.state,
                    "uuid": s.uuid,
                    # "tags": bundle.tags,
                    # "services": [s.name for s in bundle.services],
                    # "specs": f"{info['cpu_count']} CPUs, {info['ram_gb']} GB RAM, {info['storage_gb']} GB Storage, {info['pretty_name']}",
                }
            )

    if len(services) == 0:
        st.info(
            "No services installed yet. Please add a service from the templates tab."
        )
        return

    df = pd.DataFrame(
        services, columns=["name", "ip", "version", "state", "links", "uuid"]
    )
    select_server = st.dataframe(
        df,
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="service-select",
    )

    if len(select_server["selection"].get("rows", [])) == 1:
        idx = select_server["selection"]["rows"][0]
        ip = services[idx]["ip"]
        service_name = services[idx]["name"]
        service = infra.get_service(service_name)
        bundle = infra.get_bundle_by_ip(ip)
        config = infra.get_service_config(service)

        state = service.state
        c1, c2, cf, _, c3, c4 = st.columns([10, 15, 10, 20, 30, 15])
        if c1.button("Setup", disabled=state != "un-initialized"):
            with st.spinner(f"Setting up service {service_name}...", show_time=True):
                infra.setup_service(service)
            save_infra()
            st.rerun()

        if c2.button("Teardown"):
            with st.spinner(f"Deleting service {service_name}...", show_time=True):
                infra.teardown_service(service)
            save_infra()
            st.rerun()

        if cf.button("Check"):
            status = {}
            with bundle.server.get_server_connection() as conn:
                status = service.check(conn)
            st.write(status)
        # if cf.button(
        #     "Focus", disabled=state != "running" or service.uuid in infra.focus
        # ):
        #     infra.focus_service(service)
        #     save_infra()
        #     st.rerun()

        new_service_name = c3.text_input("Unique service name", service_name)
        # Add vertical space to align the button with the text input field.
        # c4.write('<div style="height: 28px;"></div>', unsafe_allow_html=True)
        st_hack_align(c4)
        if (
            c4.button("Update", icon=":material/update:")
            and new_service_name != service_name
        ):
            if new_service_name in infra.list_service_names():
                st.error("Service name must be unqiue.")
            else:
                service.name = new_service_name
                save_infra()
                st.rerun()

        with st.container(border=True):
            plot_config_nicely(config)

            # st.divider()
            callable_settings_func = config.instantiate_ui("settings")
            if callable_settings_func:
                if state == "running":
                    callable_settings_func(infra, bundle, service)
                    # save_infra()
                elif state == "un-initialized":
                    st.markdown(
                        "#### The service is not running. Please set it up first to access the settings."
                    )


def available_services():
    st.markdown("""
    Add services to your infrastructure.""")
    infra = None
    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()

    # with st.expander("Add Server"):
    configs = load_all_service_configs()

    services = []
    for service in configs:
        services.append(
            {
                "name": service.name,
                "version": service.version,
                "maintainer": service.maintainer,
                "description": service.description,
                "description_short": service.description_short,
                "links": [f"{k}: {v}" for k, v in service.links.items()],
                "requirements": [f"{k}: {v}" for k, v in service.requirements.items()],
                "ui": [f"{k}" for k, v in service.ui.items()],
                "groups": [
                    f"{k}"
                    for k, v in service.groups.items()
                    if k != "backend" and k != "service"
                ],
                "backend": [
                    f"{k}" for k, v in service.groups.get("backend", {}).items()
                ],
                "config": service,
            }
        )

    c1, c2, _ = st.columns(3)
    search_filter = c1.text_input(
        "Search",
        value="",
        key="search_filter",
        label_visibility="collapsed",
        placeholder="Search for services...",
    )
    if len(search_filter) > 0:
        services = [s for s in services if search_filter.lower() in s["name"].lower()]

    option_map = {0: "Docker only", 1: "Kubernetes only"}
    selection = c2.pills(
        "Backend Filter",
        options=option_map.keys(),
        format_func=lambda option: option_map[option],
        selection_mode="single",
        default=None,
        label_visibility="collapsed",
    )
    if selection is not None:
        if selection == 0:
            services = [s for s in services if "docker" in s["backend"]]
        elif selection == 1:
            services = [s for s in services if "kubernetes" in s["backend"]]

    df = pd.DataFrame(services)
    select = st.dataframe(
        df[
            [
                "name",
                "version",
                # "maintainer",
                # "description",
                # "links",
                # "requirements",
                "backend",
                "groups",
                "description_short",
            ]
        ],
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="avail-service-select",
    )

    if len(select["selection"].get("rows", [])) == 1:
        selected = select["selection"]["rows"][0]

        config = services[selected]["config"]
        supported_backends = list(config.groups.get("backend", {}).keys())

        # with st.form("Add Service"):
        with st.container(border=True):
            plot_config_nicely(config)

            c2, c3, c4, _ = st.columns([25, 25, 15, 35])
            select_backend = c2.selectbox(
                "Backend",
                supported_backends,
                disabled=len(supported_backends) <= 1,
            )

            bundle_candidates = infra.list_bundles_with_backend(backend=select_backend)
            bundle = c3.selectbox(
                "Server",
                [b for b in bundle_candidates if b.server.state == "running"],
                format_func=lambda x: f"{x.name}",
            )

            params = {}
            callable_setup_func = config.instantiate_ui("setup")
            if callable_setup_func:
                params = callable_setup_func(infra, bundle)

            # if st.form_submit_button("Add Service", type="primary"):
            if st.button(
                "Add Service", type="primary", disabled=params is None or not bundle
            ):
                st.info(
                    f"Adding service {config.name} {config.version} with backend {select_backend} to {bundle.name}"
                )
                ret = infra.add_service(bundle.server.ip, config, params)
                if not ret:
                    st.error("Failed to add service")
                save_infra()

        # st.write(services[selected])


# tab_avail, tab_installed = st.tabs(["Templates", "Installed"])
tab_installed, tab_avail = st.tabs(["Installed", "Templates"])
with tab_avail:
    available_services()

with tab_installed:
    installed_services()
