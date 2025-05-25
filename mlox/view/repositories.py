import pandas as pd
import streamlit as st

from datetime import datetime
from typing import cast

from mlox.session import MloxSession


def repos():
    st.markdown("""
    # Repositories
    This is where you can manage your repositories.""")

    ms = cast(MloxSession, st.session_state.mlox)
    infra = ms.infra
    bundles = infra.bundles
    with st.form("Add Repo"):
        c1, c2, c3 = st.columns([40, 40, 20])
        link = c1.text_input("GitHub Link")
        bundle = c2.selectbox("Bundle", bundles, format_func=lambda b: b.name)

        if c3.form_submit_button("Add Git Repository"):
            st.info(f"Adding {link} to {bundle.name}")
            infra.create_and_add_repo(bundle.server.ip, link)
            st.rerun()

    my_repos = []
    for bundle in bundles:
        for r in bundle.repos:
            my_repos.append(
                {
                    "ip": bundle.server.ip,
                    "server": bundle.name,
                    "name": r.name,
                    "link": r.link,
                    "relative path": r.path,
                    "added": datetime.fromisoformat(r.added_timestamp).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "modified": datetime.fromisoformat(r.modified_timestamp).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            )

    selection = st.dataframe(
        my_repos,
        hide_index=True,
        selection_mode="single-row",
        use_container_width=True,
        on_select="rerun",
    )
    if len(selection["selection"]["rows"]) > 0:
        idx = selection["selection"]["rows"][0]
        ip = my_repos[idx]["ip"]
        name = my_repos[idx]["name"]

        if st.button("Pull"):
            with st.spinner("Pulling..."):
                infra.pull_repo(ip, name)

        if st.button("Delete"):
            st.info(f"Deleting {name} (NOT IMPLEMENTED YET)")
            # infra.remove_repo(ip, repo)

        c1, c2 = st.columns(2)
        pull_method = c1.selectbox(
            "Pull Method", ["Manual", "Scheduled", "Triggered"], disabled=True
        )
        if c2.button("Set Pull Method"):
            st.info(f"Setting pull method to {pull_method} (NOT IMPLEMENTED YET)")


repos()
st.divider()
if st.button("Save Infrastructure"):
    with st.spinner("Saving infrastructure..."):
        st.session_state.mlox.save_infrastructure()
