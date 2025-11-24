import os
import logging
import mlflow  # type: ignore
import pandas as pd
import streamlit as st

from typing import Dict, cast

from mlox.infra import Infrastructure, Bundle
from mlox.services.mlflow.docker import MLFlowDockerService
from mlox.services.mlflow_mlserver.docker import MLFlowMLServerDockerService

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def setup(infra: Infrastructure, bundle: Bundle) -> Dict | None:
    params: Dict = dict()

    c1, c2, c3 = st.columns(3)

    mlflows = list()
    for bundle in infra.bundles:
        for s in bundle.services:
            if s.name.lower().startswith("mlflow"):
                mlflows.append(s)

    if len(mlflows) == 0:
        st.warning("No MLFlow server found. You need to add one first.")
        return None

    service = c1.selectbox(
        "MLFlow Registry Server",
        mlflows,
        format_func=lambda x: f"{x.name} @ {x.service_url}",
    )

    service = cast(MLFlowDockerService, service)

    # mlflow.set_tracking_uri(service.service_url)
    mlflow.set_registry_uri(service.service_url)

    os.environ["MLFLOW_TRACKING_USERNAME"] = service.ui_user
    os.environ["MLFLOW_TRACKING_PASSWORD"] = service.ui_pw
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

    client = mlflow.tracking.MlflowClient()
    models = list()
    for rm in client.search_registered_models():
        models.append(rm.name)

    my_model = c2.selectbox("Registered Models", models)

    names = list()
    filter_string = f"name='{my_model}'"
    for rm in client.search_model_versions(filter_string):
        # names.append([rm.name, rm.version, rm.current_stage, rm.source, rm.run_id])
        names.append([rm.version, rm.aliases])

    model = c3.selectbox(
        "Model Version", names, format_func=lambda x: f"Version: {x[0]} - {x[1]}"
    )

    model_uri = f"{my_model}/{model[0]}"
    st.write(model_uri)

    params["${MODEL_NAME}"] = model_uri
    params["${TRACKING_URI}"] = service.service_url
    params["${TRACKING_USER}"] = service.ui_user
    params["${TRACKING_PW}"] = service.ui_pw

    return params


def settings(
    infra: Infrastructure, bundle: Bundle, service: MLFlowMLServerDockerService
):
    st.header(f"Settings for service {service.name}")
    mlflow.set_registry_uri(service.tracking_uri)

    overview_tab, invoke_tab, versions_tab = st.tabs(
        ["Overview", "Invocation & Sample", "Model Versions"]
    )

    os.environ["MLFLOW_TRACKING_USERNAME"] = service.tracking_user
    os.environ["MLFLOW_TRACKING_PASSWORD"] = service.tracking_pw
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    client = mlflow.tracking.MlflowClient()

    with overview_tab:
        info_col, cred_col = st.columns(2)
        with info_col:
            st.subheader("Service & Tracking")
            st.markdown(
                "\n".join(
                    [
                        f"- **Service URL:** `{service.service_url}`",
                        f"- **Tracking URI:** `{service.tracking_uri}`",
                        f"- **Model Identifier:** `{service.model}`",
                        f"- **Target Path:** `{service.target_path}`",
                    ]
                )
            )
        with cred_col:
            st.subheader("Credentials")
            st.code(
                "\n".join(
                    [
                        f"MLServer user: '{service.user}'",
                        f"MLServer password: '{service.pw}'",
                        f"Tracking user: '{service.tracking_user}'",
                        f"Tracking password: '{service.tracking_pw}'",
                    ]
                ),
                language="bash",
            )
            st.caption(
                f"Traefik basic auth hash: `{service.hashed_pw.replace('$', '\\$')}`",
            )

    with invoke_tab:
        st.subheader("Invoke via cURL")

        url = service.service_url
        if url.endswith("/"):
            url = url[:-1]
        example_curl = f"""
    curl -k -u '{service.user}:{service.pw}' \\
    {url}/invocations \\
    -H 'Content-Type: application/json' \\
    -d '{{"instances": [[0.0,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.1]]}}'
        """  # .replace("\\", "  \n").strip()
        st.write(
            f"Example cURL command to invoke the model:\n```bash\n{example_curl}\n```"
        )

    with versions_tab:
        st.subheader("Registered Versions")

        names = list()
        filter_string = f"name={service.model.split('/')[0]!r}"
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
