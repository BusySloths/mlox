from __future__ import annotations

from typing import Callable

from mlox.services.airflow.ui import settings as airflow_settings
from mlox.services.feast.ui import settings as feast_settings, setup as feast_setup
from mlox.services.gcp.bq_ui import settings as gcp_bigquery_settings, setup as gcp_bigquery_setup
from mlox.services.gcp.secret_ui import settings as gcp_secret_settings, setup as gcp_secret_setup
from mlox.services.gcp.sheet_ui import settings as gcp_sheets_settings, setup as gcp_sheets_setup
from mlox.services.gcp.storage_ui import settings as gcp_storage_settings, setup as gcp_storage_setup
from mlox.services.github.ui import settings as github_settings, setup as github_setup
from mlox.services.influx.ui import settings as influx_settings
from mlox.services.k8s_dashboard.ui import settings as k8s_dashboard_settings
from mlox.services.k8s_headlamp.ui import settings as k8s_headlamp_settings
from mlox.services.kafka.ui import settings as kafka_settings
from mlox.services.kubeapps.ui import settings as kubeapps_settings
from mlox.services.litellm.ui import settings as litellm_settings, setup as litellm_setup
from mlox.services.milvus.ui import settings as milvus_settings, setup as milvus_setup
from mlox.services.minio.ui import settings as minio_settings
from mlox.services.mlflow.ui import settings as mlflow_settings
from mlox.services.mlflow_mlserver.ui import settings as mlserver_settings, setup as mlserver_setup
from mlox.services.openbao.ui import settings as openbao_settings, setup as openbao_setup
from mlox.services.otel.tui import tui_settings as otel_tui_settings
from mlox.services.otel.ui import settings as otel_settings, setup as otel_setup
from mlox.services.postgres.ui import settings as postgres_settings, setup as postgres_setup
from mlox.services.redis.ui import settings as redis_settings
from mlox.services.repo_deploy.ui import settings as repo_deploy_settings, setup as repo_deploy_setup
from mlox.services.tsm.ui import settings as tsm_settings
from mlox.servers.ubuntu.ui_docker import settings as ubuntu_docker_settings, setup as ubuntu_docker_setup
from mlox.servers.ubuntu.ui_k3s import settings as ubuntu_k3s_settings, setup as ubuntu_k3s_setup
from mlox.servers.ubuntu.ui_native import settings as ubuntu_native_settings, setup as ubuntu_native_setup
from mlox.servers.ubuntu.ui_simple import settings as ubuntu_simple_settings, setup as ubuntu_simple_setup

_SETTINGS_RENDERERS: dict[str, Callable] = {
    "airflow-2.9.2-docker": airflow_settings,
    "airflow-3.1.3-docker": airflow_settings,
    "feast-0.54.0": feast_settings,
    "gcp-bigquery-0.1.0": gcp_bigquery_settings,
    "gcp-secret-manager-0.1.0": gcp_secret_settings,
    "gcp-sheets-0.1.0": gcp_sheets_settings,
    "gcp-storage-0.1.0": gcp_storage_settings,
    "github-repo-0.1-beta-docker": github_settings,
    "influx-1.11.8-docker": influx_settings,
    "k8s-dashboard-newest-k3s": k8s_dashboard_settings,
    "headlamp-newest-k3s": k8s_headlamp_settings,
    "kafka-3.7.0-docker": kafka_settings,
    "kafka-4.1.0-docker": kafka_settings,
    "kubeapps-newest-k3s": kubeapps_settings,
    "litellm-ollama-1.77.7-docker": litellm_settings,
    "milvus-2.5-docker": milvus_settings,
    "minio-release-2025-07-23-docker": minio_settings,
    "mlflow-2.22.0-docker": mlflow_settings,
    "mlflow-3.8.1-docker": mlflow_settings,
    "mlflow-mlserver-2.22.0-docker": mlserver_settings,
    "mlflow-mlserver-3.8.1-k3s": mlserver_settings,
    "mlflow-mlserver-3.8.1-docker": mlserver_settings,
    "openbao-docker": openbao_settings,
    "otel-0.127.0-docker": otel_settings,
    "otel-0.146.1-docker": otel_settings,
    "postgres-16-bullseye-docker": postgres_settings,
    "redis-8-bookworm-docker": redis_settings,
    "repo-deploy-0.1-beta-docker": repo_deploy_settings,
    "tsm-0.1-beta": tsm_settings,
    "ubuntu-docker-24.04-server": ubuntu_docker_settings,
    "ubuntu-k3s-24.04-server": ubuntu_k3s_settings,
    "ubuntu-native-24.04-server": ubuntu_native_settings,
    "ubuntu-simple-24.04-server": ubuntu_simple_settings,
}
_SETUP_RENDERERS: dict[str, Callable] = {
    "feast-0.54.0": feast_setup,
    "gcp-bigquery-0.1.0": gcp_bigquery_setup,
    "gcp-secret-manager-0.1.0": gcp_secret_setup,
    "gcp-sheets-0.1.0": gcp_sheets_setup,
    "gcp-storage-0.1.0": gcp_storage_setup,
    "github-repo-0.1-beta-docker": github_setup,
    "litellm-ollama-1.77.7-docker": litellm_setup,
    "milvus-2.5-docker": milvus_setup,
    "mlflow-mlserver-2.22.0-docker": mlserver_setup,
    "mlflow-mlserver-3.8.1-k3s": mlserver_setup,
    "mlflow-mlserver-3.8.1-docker": mlserver_setup,
    "openbao-docker": openbao_setup,
    "otel-0.127.0-docker": otel_setup,
    "otel-0.146.1-docker": otel_setup,
    "postgres-16-bullseye-docker": postgres_setup,
    "repo-deploy-0.1-beta-docker": repo_deploy_setup,
    "ubuntu-docker-24.04-server": ubuntu_docker_setup,
    "ubuntu-k3s-24.04-server": ubuntu_k3s_setup,
    "ubuntu-native-24.04-server": ubuntu_native_setup,
    "ubuntu-simple-24.04-server": ubuntu_simple_setup,
}
_TUI_SETTINGS_RENDERERS: dict[str, Callable] = {
    "otel-0.127.0-docker": otel_tui_settings,
    "otel-0.146.1-docker": otel_tui_settings,
}


def get_settings_renderer(config_id: str) -> Callable | None:
    return _SETTINGS_RENDERERS.get(config_id)


def get_setup_renderer(config_id: str) -> Callable | None:
    return _SETUP_RENDERERS.get(config_id)


def get_tui_settings_renderer(config_id: str) -> Callable | None:
    return _TUI_SETTINGS_RENDERERS.get(config_id)
