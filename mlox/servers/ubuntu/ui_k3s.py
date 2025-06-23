import os
import streamlit as st

from typing import Dict, cast

from mlox.infra import Infrastructure, Bundle


def setup(
    self,
    controller: Any | None = None,
) -> None:
    if backend == "docker":
        self.server.setup_docker()
        self.server.start_docker_runtime()
    elif backend == "kubernetes":
        self.server.setup_kubernetes()
        self.server.start_kubernetes_runtime()
    elif backend == "kubernetes-agent" and controller:
        stats = controller.server.get_kubernetes_status()
        if "k3s.token" not in stats:
            logging.error(
                "Token is missing in controller stats ip: %s", controller.server.ip
            )
            return
        url = f"https://{controller.server.ip}:6443"
        token = stats["k3s.token"]
        self.server.setup_kubernetes(controller_url=url, controller_token=token)
        self.server.start_kubernetes_runtime()
        cluster_name = f"k8s-{controller.name}"
        self.tags.append(cluster_name)
        if cluster_name not in controller.tags:
            controller.tags.append(cluster_name)
    self.status = backend


def setup(infra: Infrastructure) -> Dict:
    params = dict()

    st.header("Setup K3S Kubernetes")

    service = st.selectbox(
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


def settings(
    infra: Infrastructure, bundle: Bundle, service: MLFlowMLServerDockerService
):
    st.header(f"Settings for service {service.name}")
