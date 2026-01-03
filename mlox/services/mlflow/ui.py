import pandas as pd
import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.services.mlflow.docker import MLFlowDockerService


def settings(infra: Infrastructure, bundle: Bundle, service: MLFlowDockerService):
    st.write(f"UI User: {service.ui_user}")
    st.write(f'UI Password: "{service.ui_pw}"')

    st.link_button(
        "Open MLflow UI",
        url=service.service_url,
        icon=":material/open_in_new:",
        help="Open the MLflow UI in a new tab",
    )

    models = service.list_models()
    model_names = list({m["Model"]: m for m in models}.keys())

    c1, c2 = st.columns(2)
    c1.metric("Registered Models", len(model_names))
    c2.metric("Model Versions", len(models))

    tab_versions, tab_registry, tab_examples = st.tabs(
        ["Model Versions", "Registries", "Notebook Examples"]
    )

    with tab_versions:
        if not models:
            st.info("No model versions found.")
        else:
            st.dataframe(
                pd.DataFrame(models).drop(columns=["Tags"]),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Open": st.column_config.LinkColumn(display_text="Open in UI"),
                },
            )

    with tab_registry:
        registry_rows = []
        for name in model_names:
            registered_models = [m for m in models if m["Model"] == name]
            latest = [
                lv
                for lv in registered_models
                if lv["Version"]
                == str(max(int(m["Version"]) for m in registered_models))
            ][0]
            registry_rows.append(
                {
                    "Name": name,
                    "Description": latest["Description"] or "",
                    "Tags": [f"{k}:{v}" for k, v in (latest["Tags"] or {}).items()],
                    "Latest Versions": latest["Version"] or "-",
                }
            )
        if not registry_rows:
            st.info("No registered models yet.")
        else:
            st.dataframe(
                pd.DataFrame(registry_rows),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Tags": st.column_config.ListColumn(),
                },
            )

    with tab_examples:
        st.markdown(
            "#### Notebook Examples\n"
            "You can find sample notebooks in the "
            "[mlox repository](https://github.com/busysloths/mlox). "
            "Initialize MLflow access like so:"
        )
        st.code(
            "\n".join(
                [
                    "import os",
                    "import mlflow",
                    "",
                    f'mlflow.set_tracking_uri("{service.service_url}")',
                    f'os.environ["MLFLOW_TRACKING_USERNAME"] = "{service.ui_user}"',
                    f'os.environ["MLFLOW_TRACKING_PASSWORD"] = "{service.ui_pw}"',
                    'os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"',
                ]
            ),
            language="python",
            line_numbers=True,
        )
