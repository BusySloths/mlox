from __future__ import annotations

import importlib

from mlox.ui.registry import register

_REGISTERED = False

_STREAMLIT_SERVICE_BINDINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "mlox.view.services.airflow": {
        "config_ids": ("airflow-2.9.2-docker", "airflow-3.1.3-docker"),
        "function_names": ("settings",),
    },
    "mlox.view.services.feast": {
        "config_ids": ("feast-0.54.0",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.gcp.bq": {
        "config_ids": ("gcp-bigquery-0.1.0",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.gcp.secret": {
        "config_ids": ("gcp-secret-manager-0.1.0",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.gcp.sheet": {
        "config_ids": ("gcp-sheets-0.1.0",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.gcp.storage": {
        "config_ids": ("gcp-storage-0.1.0",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.github": {
        "config_ids": ("github-repo-0.1-beta-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.influx": {
        "config_ids": ("influx-1.11.8-docker",),
        "function_names": ("settings",),
    },
    "mlox.view.services.k8s_dashboard": {
        "config_ids": ("k8s-dashboard-newest-k3s",),
        "function_names": ("settings",),
    },
    "mlox.view.services.k8s_headlamp": {
        "config_ids": ("headlamp-newest-k3s",),
        "function_names": ("settings",),
    },
    "mlox.view.services.kafka": {
        "config_ids": ("kafka-3.7.0-docker", "kafka-4.1.0-docker"),
        "function_names": ("settings",),
    },
    "mlox.view.services.kubeapps": {
        "config_ids": ("kubeapps-newest-k3s",),
        "function_names": ("settings",),
    },
    "mlox.view.services.kubeflow": {
        "config_ids": ("kubeflow-1.10.1-k3s",),
        "function_names": ("settings",),
    },
    "mlox.view.services.litellm": {
        "config_ids": ("litellm-ollama-1.77.7-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.milvus": {
        "config_ids": ("milvus-2.5-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.minio": {
        "config_ids": ("minio-release-2025-07-23-docker",),
        "function_names": ("settings",),
    },
    "mlox.view.services.mlflow": {
        "config_ids": ("mlflow-2.22.0-docker", "mlflow-3.8.1-docker"),
        "function_names": ("settings",),
    },
    "mlox.view.services.mlflow_mlserver": {
        "config_ids": (
            "mlflow-mlserver-2.22.0-docker",
            "mlflow-mlserver-3.8.1-k3s",
            "mlflow-mlserver-3.8.1-docker",
        ),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.mlflow_gateway": {
        "config_ids": ("mlflow-gateway-3.8.1-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.openbao": {
        "config_ids": ("openbao-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.ollama": {
        "config_ids": ("ollama-0.23.3-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.otel": {
        "config_ids": ("otel-0.127.0-docker", "otel-0.146.1-docker"),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.postgres": {
        "config_ids": ("postgres-16-bullseye-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.redis": {
        "config_ids": ("redis-8-bookworm-docker",),
        "function_names": ("settings",),
    },
    "mlox.view.services.registry": {
        "config_ids": ("registry-3-docker",),
        "function_names": ("settings",),
    },
    "mlox.view.services.repo_deploy": {
        "config_ids": ("repo-deploy-0.1-beta-docker",),
        "function_names": ("settings", "setup"),
    },
    "mlox.view.services.tsm": {
        "config_ids": ("tsm-0.1-beta",),
        "function_names": ("settings",),
    },
}


def register_builtin_streamlit_services() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    _REGISTERED = True
    for module_path, binding in _STREAMLIT_SERVICE_BINDINGS.items():
        module = importlib.import_module(module_path)
        for function_name in binding["function_names"]:
            handler = getattr(module, function_name, None)
            if handler is None:
                continue
            for config_id in binding["config_ids"]:
                register(
                    config_id=config_id,
                    frontend="streamlit",
                    function_name=function_name,
                    handler=handler,
                )
