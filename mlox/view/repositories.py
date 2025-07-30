import pandas as pd
import streamlit as st

from datetime import datetime
from typing import cast

# from mlox.session import MloxSession
from mlox.infra import Infrastructure


def save_infra():
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()


def manage_repositories():
    st.markdown("""
    # Repositories
    This is where you can manage your repositories.""")

    infra = None
    try:
        infra = cast(Infrastructure, st.session_state.mlox.infra)
    except BaseException:
        st.error("Could not load infrastructure configuration.")
        st.stop()
    # bundles = infra.bundles
    # with st.form("Add Repo"):
    #     c1, c2, c3 = st.columns([40, 40, 20])
    #     link = c1.text_input("GitHub Link")
    #     bundle = c2.selectbox("Bundle", bundles, format_func=lambda b: b.name)

    #     if c3.form_submit_button("Add Git Repository"):
    #         st.info(f"Adding {link} to {bundle.name}")
    #         infra.create_and_add_repo(bundle.server.ip, link)
    #         st.rerun()

    my_repos = []
    for r in infra.filter_by_group("repository"):
        bundle = infra.get_bundle_by_service(r)
        if not bundle:
            continue
        my_repos.append(
            {
                "ip": bundle.server.ip,
                "server": bundle.name,
                "name": r.name,
                "state": r.state,
                "link": r.link,
                "path": r.target_path,
                "added": datetime.fromisoformat(r.created_timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "modified": datetime.fromisoformat(r.modified_timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "repo": r,
            }
        )

    df = pd.DataFrame(
        my_repos,
        columns=[
            "ip",
            "server",
            "name",
            "state",
            "link",
            "path",
            "added",
            "modified",
            "repo",
        ],
    )
    selection = st.dataframe(
        df[["name", "state", "link", "server", "path", "added", "modified"]],
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        # ip = my_repos[idx]["ip"]
        # name = my_repos[idx]["name"]
        repo = my_repos[idx]["repo"]

        config = infra.get_service_config(repo)

        callable_settings_func = config.instantiate_ui("settings")
        # if callable_settings_func and repo.state == "running":
        if callable_settings_func:
            callable_settings_func(infra, bundle, repo)

        # if st.button("Delete"):
        #     with st.spinner(f"Deleting {name}..."):
        #         infra.teardown_service(repo)
        #     save_infra()
        #     st.rerun()


manage_repositories()
