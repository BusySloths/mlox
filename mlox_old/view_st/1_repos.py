import pandas as pd
import streamlit as st

from mlox_old.configs_old import Infrastructure
from mlox.remote import git_clone


def run():
    # st.set_page_config(page_title="VPS Install Page", page_icon="🌍")
    st.markdown("# Repos")

    servers = Infrastructure().infrastructure.servers
    target_ip = st.selectbox("Choose Server", list(servers.keys()))
    server = servers[target_ip]

    public_key = st.text_area(
        "Add this public key to your private Github repos.", "public key", disabled=True
    )

    df = pd.DataFrame(
        [
            {
                "repo url": "https://github.com/sheetcloud/sheetcloud",
                "install path": "repos/",
                "update": True,
                "Interval": "Every 5min",
            },
            {
                "repo url": "st.balloons",
                "install path": "repos/",
                "update": True,
                "Interval": "Every 5min",
            },
        ]
    )
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Interval": st.column_config.SelectboxColumn(
                "Interval",
                help="How often will airflow pull the newest version of the repo.",
                width="medium",
                options=[
                    "Every 5min",
                    "Every 1hour",
                    "Every 1day",
                ],
                default=1,
                required=True,
            )
        },
    )

    if st.button("Git Clone"):
        with server as conn:
            for i in edited_df.iterrows():
                repo_url = i[1]["repo url"]
                install_path = i[1]["install path"]
                print(repo_url, install_path)
                git_clone(conn, repo_url, f"/home/{conn.user}/{install_path}")


run()
