import streamlit as st

from typing import cast

from mlox.infra import Infrastructure
from mlox.config import load_all_service_configs


def installed_services():
    st.markdown("""
    # Services
    This is where you can manage your services.""")
    infra = cast(Infrastructure, st.session_state.mlox.infra)

    # with st.expander("Add Server"):
    # with st.form("add_service"):
    configs = load_all_service_configs("./stacks")
    c1, c2, c3, c4 = st.columns([20, 20, 20, 10])
    config = c1.selectbox(
        "Service Configuration",
        configs,
        format_func=lambda x: f"{x.name} {x.version}",
    )
    select_backend = c2.selectbox(
        "Backend",
        list(config.build),
        format_func=lambda x: f"{x} Backend",
        key="select_backedn",
    )
    bundle = c3.selectbox(
        "Server",
        infra.list_bundles_with_backend(backend=select_backend),
        format_func=lambda x: f"{x.name} {x.server.ip}",
    )
    if c4.button("Add Service"):
        st.info(
            f"Adding service {config.name} {config.version} with backend {select_backend} to {bundle.name}"
        )

    st.markdown("### Service List")

    services = []
    for bundle in infra.bundles:
        for service in bundle.services:
            services.append(
                {
                    "ip": bundle.server.ip,
                    "name": service.name,
                    "version": service.version,
                    # "status": [bundle.status],
                    # "tags": bundle.tags,
                    # "services": [s.name for s in bundle.services],
                    # "specs": f"{info['cpu_count']} CPUs, {info['ram_gb']} GB RAM, {info['storage_gb']} GB Storage, {info['pretty_name']}",
                }
            )

    select_server = st.dataframe(
        services,
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="service-select",
    )

    if len(select_server["selection"].get("rows", [])) == 1:
        selected_server = services[select_server["selection"]["rows"][0]]["ip"]
        bundle = infra.get_bundle_by_ip(selected_server)

        # server_management(infra, selected_server)
        c1, c2, c3 = st.columns([40, 50, 10])


def available_services():
    st.markdown("""
    # Services
    This is where you can manage your services.""")
    infra = cast(Infrastructure, st.session_state.mlox.infra)

    # with st.expander("Add Server"):
    configs = load_all_service_configs("./stacks")
    st.markdown("### Available Services")

    services = []
    for service in configs:
        services.append(
            {
                "name": service.name,
                "version": service.version,
                "maintainer": service.maintainer,
                "description": service.description,
                "links": [f"{k}: {v}" for k, v in service.links.items()],
                "requirements": [f"{k}: {v}" for k, v in service.requirements.items()],
                "Build": [f"{k}" for k, v in service.build.items()],
            }
        )

    select = st.dataframe(
        services,
        use_container_width=True,
        selection_mode="single-row",
        hide_index=True,
        on_select="rerun",
        key="avail-service-select",
    )

    if len(select["selection"].get("rows", [])) == 1:
        selected = select["selection"]["rows"][0]
        st.write(services[selected])


tab_avail, tab_installed = st.tabs(["Available", "Installed"])
with tab_avail:
    available_services()

with tab_installed:
    installed_services()

st.divider()
if st.button("Save Infrastructure"):
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()
