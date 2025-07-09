import os
import mlflow  # type: ignore
import pandas as pd
import streamlit as st

from mlox.services.mlflow.docker import MLFlowDockerService
from mlox.infra import Infrastructure, Bundle


def settings(infra: Infrastructure, bundle: Bundle, service: MLFlowDockerService):
    # st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    st.write(f"UI User: {service.ui_user}")
    st.write(f'UI Password: "{service.ui_pw}"')
    st.link_button(
        "Open MLflow UI",
        url=service.service_url,
        icon=":material/open_in_new:",
        help="Open the MLflow UI in a new tab",
    )

    # mlflow.set_tracking_uri(service.service_url)
    mlflow.set_registry_uri(service.service_url)

    os.environ["MLFLOW_TRACKING_USERNAME"] = service.ui_user
    os.environ["MLFLOW_TRACKING_PASSWORD"] = service.ui_pw
    # os.environ["MLFLOW_FLASK_SERVER_SECRET_KEY"] = "my-secret-key"
    # os.environ['MLFLOW_TRACKING_TOKEN'] = 'b9efe95a-ae53-50de-92a3-882de5c90128'
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

    tab_models, tab_nb_exm = st.tabs(["Models", "Notebooks Examples"])
    with tab_nb_exm:
        st.markdown(
            "#### Notebooks Examples\n"
            "You can find some example notebooks in the [mlox repository](https://github.com/nicococo/mlox) "
            "Init your scripts as follows to connect to the MLflow server:"
        )
        st.code(
            f'''
import os
import mlflow
mlflow.set_tracking_uri("{service.service_url}")
os.environ['MLFLOW_TRACKING_USERNAME'] = \'{service.ui_user}\'
os.environ['MLFLOW_TRACKING_PASSWORD'] = \'{service.ui_pw}\'
os.environ['MLFLOW_TRACKING_INSECURE_TLS'] = \'true\' ''',
            language="python",
            line_numbers=True,
        )

    with tab_models:
        names = list()
        client = mlflow.tracking.MlflowClient()
        filter_string = f"name='live1'"
        for rm in client.search_model_versions(filter_string):
            # names.append([rm.name, rm.version, rm.current_stage, rm.source, rm.run_id])
            names.append(
                {
                    # "name": rm.name,
                    "alias": [str(a) for a in rm.aliases],
                    "version": rm.version,
                    "tags": [f"{k}:{v}" for k, v in rm.tags.items()],
                    "current_stage": rm.current_stage,
                    "creation_timestamp": rm.creation_timestamp,
                    "run_id": rm.run_id,
                    "status": rm.status,
                    "last_updated_timestamp": rm.last_updated_timestamp,
                    "description": rm.description,
                    # "user_id": rm.user_id,
                    "run_link": f"{service.service_url}#/experiments/{rm.run_id}/runs/{rm.run_id}",
                }
            )
        if len(names) == 0:
            st.info("No model variants in registry `live1` found.")
        else:
            st.write(pd.DataFrame(names))
