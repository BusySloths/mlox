import os
import mlflow  # type: ignore
import pandas as pd
import streamlit as st

from typing import Dict

from mlox.services.mlflow.docker import MLFlowDockerService
from mlox.infra import Infrastructure, Bundle


def setup(infra: Infrastructure, bundle: Bundle) -> Dict:
    params = dict()

    mlflows = list()
    for bundle in infra.bundles:
        for statefule_service in bundle.services:
            if statefule_service.service.name.lower().startswith("mlflow"):
                mlflows.append(statefule_service.service)

    service = st.selectbox(
        "MLFlow Registry Server",
        mlflows,
        format_func=lambda x: f"{x.name} @ {x.service_url}",
    )

    # mlflow.set_tracking_uri(service.service_url)
    mlflow.set_registry_uri(service.service_url)

    os.environ["MLFLOW_TRACKING_USERNAME"] = service.ui_user
    os.environ["MLFLOW_TRACKING_PASSWORD"] = service.ui_pw
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

    client = mlflow.tracking.MlflowClient()
    models = list()
    for rm in client.search_registered_models():
        models.append(rm.name)

    my_model = st.selectbox("Registered Models", models)

    names = list()
    filter_string = f"name='{my_model}'"
    for rm in client.search_model_versions(filter_string):
        # names.append([rm.name, rm.version, rm.current_stage, rm.source, rm.run_id])
        names.append([rm.version, rm.aliases])

    model = st.selectbox(
        "Model Version", names, format_func=lambda x: f"Version: {x[0]} - {x[1]}"
    )

    model_uri = f"{my_model}/{model[0]}"
    st.write(model_uri)

    params["${MODEL_NAME}"] = model_uri
    params["${TRACKING_URI}"] = service.service_url
    params["${TRACKING_USER}"] = service.ui_user
    params["${TRACKING_PW}"] = service.ui_pw

    return params


def settings(infra: Infrastructure, bundle: Bundle, service: MLFlowDockerService):
    st.header(f"Settings for service {service.name}")
    # st.write(f"IP: {bundle.server.ip}")

    # mlflow.set_tracking_uri(service.service_url)
    mlflow.set_registry_uri(service.service_url)

    os.environ["MLFLOW_TRACKING_USERNAME"] = service.ui_user
    os.environ["MLFLOW_TRACKING_PASSWORD"] = service.ui_pw
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

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
    st.write(pd.DataFrame(names))
