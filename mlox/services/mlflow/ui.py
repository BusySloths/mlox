import os
from datetime import datetime

import mlflow  # type: ignore
import pandas as pd
import streamlit as st

from mlox.infra import Bundle, Infrastructure
from mlox.services.mlflow.docker import MLFlowDockerService
from mlox.services.utils_ui import save_to_secret_store


def settings(infra: Infrastructure, bundle: Bundle, service: MLFlowDockerService):
    st.write(f"UI User: {service.ui_user}")
    st.write(f'UI Password: "{service.ui_pw}"')
    # save_to_secret_store(
    #     infra,
    #     f"MLOX_MLFLOW_{service.name.upper()}",
    #     {
    #         "url": service.service_url,
    #         "user": service.ui_user,
    #         "password": service.ui_pw,
    #     },
    # )

    st.link_button(
        "Open MLflow UI",
        url=service.service_url,
        icon=":material/open_in_new:",
        help="Open the MLflow UI in a new tab",
    )

    mlflow.set_registry_uri(service.service_url)
    os.environ["MLFLOW_TRACKING_USERNAME"] = service.ui_user
    os.environ["MLFLOW_TRACKING_PASSWORD"] = service.ui_pw
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

    client = mlflow.tracking.MlflowClient()
    try:
        registered_models = client.search_registered_models()
    except Exception as exc:  # pragma: no cover - defensive for UI failures
        st.error(f"Failed to load MLflow registry data: {exc}")
        return
    total_models = len(registered_models)
    total_versions = sum(
        len(client.search_model_versions(f"name='{rm.name}'"))
        for rm in registered_models
    )

    c1, c2 = st.columns(2)
    c1.metric("Registered Models", total_models)
    c2.metric("Model Versions", total_versions)

    tab_versions, tab_registry, tab_examples = st.tabs(
        ["Model Versions", "Registries", "Notebook Examples"]
    )

    def _fmt_ts(ts: int | None) -> str:
        if not ts:
            return ""
        return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")

    with tab_versions:
        version_rows = []
        for rm in registered_models:
            for version in client.search_model_versions(f"name='{rm.name}'"):
                version_rows.append(
                    {
                        "Model": version.name,
                        "Version": version.version,
                        "Stage": version.current_stage or "-",
                        "Aliases": ", ".join(version.aliases or []),
                        "Status": version.status,
                        "Updated": _fmt_ts(version.last_updated_timestamp),
                        "Run ID": version.run_id,
                        "Open": f"{service.service_url}#/models/{version.name}/versions/{version.version}",
                    }
                )
        if not version_rows:
            st.info("No model versions found in this registry.")
        else:
            st.dataframe(
                pd.DataFrame(version_rows),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Open": st.column_config.LinkColumn(display_text="Open in UI")
                },
            )

    with tab_registry:
        registry_rows = []
        for rm in registered_models:
            latest = ", ".join(
                f"{lv.name}:{lv.current_stage}" for lv in (rm.latest_versions or [])
            )
            registry_rows.append(
                {
                    "Name": rm.name,
                    "Description": rm.description or "",
                    "Tags": ", ".join(f"{k}:{v}" for k, v in (rm.tags or {}).items()),
                    "Latest Versions": latest or "-",
                }
            )
        if not registry_rows:
            st.info("No registered models yet.")
        else:
            st.dataframe(
                pd.DataFrame(registry_rows),
                hide_index=True,
                use_container_width=True,
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
