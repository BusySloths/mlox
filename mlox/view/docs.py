import pandas as pd
import streamlit as st


def help():
    st.markdown("""
    # Help and Documentation
    Quick access to the documentation and help resources. 
    Here you can find links to the documentation of the services you have installed.
                
    For more information on **MLOX** visit our [Project page](https://mlox.org) 
    and our [Github page](https://github.com/busysloths/mlox)                 
    """)
    ms = st.session_state["mlox"]
    docs_dict = dict()

    infra = ms.infra
    for b in infra.bundles:
        for s in b.services:
            config = infra.get_service_config(s)
            docs_dict[config.name] = [
                config.links.get("project", ""),
                config.links.get("documentation", ""),
            ]

    st.dataframe(
        pd.DataFrame.from_dict(
            docs_dict,
            orient="index",
            columns=["Project Link", "Documentation Link"],
        ),
        column_config={
            "Project Link": st.column_config.LinkColumn(),
            "Documentation Link": st.column_config.LinkColumn(),
        },
        use_container_width=True,
        key="help-select",
    )


help()
