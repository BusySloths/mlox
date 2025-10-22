import pytest

from mlox.services.kafka.docker import KafkaDockerService
from mlox.services.airflow.docker import AirflowDockerService
from mlox.services.feast.docker import FeastDockerService
from mlox.services.gcp.bq_service import GCPBigQueryService
from mlox.services.gcp.secret_service import GCPSecretService
from mlox.services.gcp.sheet_service import GCPSpreadsheetsService
from mlox.services.gcp.storage_service import GCPStorageService
from mlox.services.github.service import GithubRepoService
from mlox.services.influx.docker import InfluxDockerService
from mlox.services.k8s_dashboard.k8s import K8sDashboardService
from mlox.services.k8s_headlamp.k8s import K8sHeadlampService
from mlox.services.kubeapps.k8s import KubeAppsService
from mlox.services.litellm.docker import LiteLLMDockerService
from mlox.services.milvus.docker import MilvusDockerService
from mlox.services.minio.docker import MinioDockerService
from mlox.services.mlflow.docker import MLFlowDockerService
from mlox.services.mlflow_mlserver.docker import MLFlowMLServerDockerService
from mlox.services.otel.docker import OtelDockerService
from mlox.services.postgres.docker import PostgresDockerService
from mlox.services.redis.docker import RedisDockerService
from mlox.services.tsm.service import TSMService


BASE_KWARGS = {
    "name": "test-service",
    "service_config_id": "cfg-id",
    "template": "/tmp/template",
    "target_path": "/tmp/target",
}


def _set_github_deploy_key(service: GithubRepoService) -> None:
    service.deploy_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQD"


SERVICE_CASES = [
    (
        AirflowDockerService,
        {
            "path_dags": "/dags",
            "path_output": "/output",
            "ui_user": "airflow",
            "ui_pw": "airflowpw",
            "port": "8080",
        },
        {
            "airflow_ui_credentials": {
                "username": "airflow",
                "password": "airflowpw",
            },
        },
        None,
    ),
    (
        RedisDockerService,
        {"pw": "redispass", "port": "6379"},
        {
            "redis_connection": {
                "host": "",
                "port": "6379",
                "password": "redispass",
                "certificate": "",
            }
        },
        None,
    ),
    (
        KafkaDockerService,
        {"ssl_password": "sslpass", "ssl_port": "9093"},
        {"kafka_ssl_credentials": {"password": "sslpass"}},
        None,
    ),
    (
        KubeAppsService,
        {},
        {},
        None,
    ),
    (
        FeastDockerService,
        {
            "dockerfile": "Dockerfile",
            "registry_port": "6565",
            "project_name": "demo_project",
            "online_store_uuid": "online_uuid",
            "offline_store_uuid": "offline_uuid",
        },
        {
            "feast_registry": {
                "registry_host": "",
                "registry_port": "6565",
                "certificate": "",
                "project": "demo_project",
                "online_store_uuid": "online_uuid",
                "offline_store_uuid": "offline_uuid",
            }
        },
        None,
    ),
    (
        LiteLLMDockerService,
        {
            "ollama_script": "entrypoint.sh",
            "litellm_config": "config.yaml",
            "ui_user": "litellm",
            "ui_pw": "litellm-pass",
            "ui_port": "8000",
            "service_port": "8081",
            "slack_webhook": "https://hooks.slack.com/services/test",
            "api_key": "llm-api-key",
            "openai_key": "openai-key",
        },
        {
            "litellm_api_access": {"api_key": "llm-api-key"},
            "litellm_slack_alerting": {
                "webhook_url": "https://hooks.slack.com/services/test",
            },
            "litellm_ui_credentials": {
                "username": "litellm",
                "password": "litellm-pass",
            },
        },
        None,
    ),
    (
        GithubRepoService,
        {"link": "https://github.com/example/repo", "is_private": True},
        {
            "github_deploy_key": {
                "key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQD",
            },
        },
        _set_github_deploy_key,
    ),
    (
        MLFlowMLServerDockerService,
        {
            "dockerfile": "Dockerfile",
            "port": "5005",
            "model": "model",
            "tracking_uri": "https://mlflow.example.com",
            "tracking_user": "tracking",
            "tracking_pw": "tracking-pass",
            "user": "mlserver",
            "pw": "mlserver-pass",
        },
        {
            "mlserver_basic_auth": {
                "username": "mlserver",
                "password": "mlserver-pass",
            },
            "mlflow_tracking_credentials": {
                "username": "tracking",
                "password": "tracking-pass",
            },
        },
        None,
    ),
    (
        InfluxDockerService,
        {
            "user": "influx",
            "pw": "influx-pass",
            "port": "8086",
            "token": "influx-token",
        },
        {
            "influx_admin_credentials": {
                "username": "influx",
                "password": "influx-pass",
                "token": "influx-token",
            },
        },
        None,
    ),
    (
        GCPStorageService,
        {"secret_name": "storage-key", "secret_manager_uuid": "uuid"},
        {},
        None,
    ),
    (
        MinioDockerService,
        {
            "root_user": "minio",
            "root_password": "minio-pass",
            "api_port": "9000",
            "console_port": "9001",
        },
        {
            "minio_root_credentials": {
                "username": "minio",
                "password": "minio-pass",
            },
        },
        None,
    ),
    (
        MilvusDockerService,
        {
            "config": "milvus.yaml",
            "user": "milvus",
            "pw": "milvus-pass",
            "port": "19530",
        },
        {
            "milvus_credentials": {
                "username": "milvus",
                "password": "milvus-pass",
            },
        },
        None,
    ),
    (
        TSMService,
        {"pw": "tsm-pass", "server_uuid": "server-uuid"},
        {"tsm_secrets_vault": {"password": "tsm-pass"}},
        None,
    ),
    (
        GCPSecretService,
        {"secret_name": "gcp-secret", "secret_manager_uuid": "uuid"},
        {},
        None,
    ),
    (
        K8sDashboardService,
        {},
        {},
        None,
    ),
    (
        GCPSpreadsheetsService,
        {"secret_name": "sheets", "secret_manager_uuid": "uuid"},
        {},
        None,
    ),
    (
        GCPBigQueryService,
        {"secret_name": "bq", "secret_manager_uuid": "uuid"},
        {},
        None,
    ),
    (
        PostgresDockerService,
        {
            "user": "postgres",
            "pw": "postgres-pass",
            "db": "postgres-db",
            "port": "5432",
        },
        {
            "postgres_connection": {
                "host": "",
                "port": "5432",
                "database": "postgres-db",
                "username": "postgres",
                "password": "postgres-pass",
                "certificate": "",
            }
        },
        None,
    ),
    (
        MLFlowDockerService,
        {"ui_user": "mlflow", "ui_pw": "mlflow-pass", "port": "5000"},
        {
            "mlflow_ui_credentials": {
                "username": "mlflow",
                "password": "mlflow-pass",
            },
        },
        None,
    ),
    (
        OtelDockerService,
        {
            "relic_endpoint": "https://otlp.nr.example.com",
            "relic_key": "nr-key",
            "config": "otel.yaml",
            "port_grpc": "4317",
            "port_http": "4318",
            "port_health": "13133",
        },
        {
            "new_relic_exporter": {
                "license_key": "nr-key",
                "endpoint": "https://otlp.nr.example.com",
            },
        },
        None,
    ),
    (
        K8sHeadlampService,
        {},
        {},
        None,
    ),
]


@pytest.mark.parametrize(
    "service_cls, extra_kwargs, expected, post_init",
    SERVICE_CASES,
)
def test_service_get_secrets(service_cls, extra_kwargs, expected, post_init):
    kwargs = {**BASE_KWARGS, **extra_kwargs}
    service = service_cls(**kwargs)
    if post_init is not None:
        post_init(service)
    assert service.get_secrets() == expected
