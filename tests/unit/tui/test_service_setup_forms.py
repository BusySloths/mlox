"""TUI service setup form tests."""

from __future__ import annotations

from types import SimpleNamespace

from mlox.service import ServiceCapability
from mlox.tui.services import setup as service_setup


def test_postgres_setup_spec_materializes_database_name() -> None:
    spec = service_setup.postgres(None, None, SimpleNamespace(name="Postgres"))

    params = spec.params({"database": "analytics"}, None)

    assert params == {"${POSTGRES_DB}": "analytics"}


def test_github_setup_spec_materializes_public_and_private_links() -> None:
    spec = service_setup.github_repo(None, None, SimpleNamespace(name="GitHub"))

    public = spec.params(
        {"owner": "org", "repo": "repo", "private": "false"},
        None,
    )
    private = spec.params(
        {"owner": "org", "repo": "repo", "private": "true"},
        None,
    )

    assert public["${GITHUB_LINK}"] == "https://github.com/org/repo.git"
    assert public["${GITHUB_PRIVATE}"] == "False"
    assert private["${GITHUB_LINK}"] == "git@github.com:org/repo.git"
    assert private["${GITHUB_PRIVATE}"] == "True"


def test_mlflow_gateway_setup_spec_uses_registry_secrets() -> None:
    registry = SimpleNamespace(
        uuid="registry-1",
        name="MLflow",
        capabilities={ServiceCapability.MODEL_REGISTRY},
        get_secrets=lambda: {
            "username": "mlflow",
            "password": "pw",
            "service_url": "https://mlflow.test",
        },
    )
    infra = SimpleNamespace(
        services=lambda: [registry],
        get_service_by_uuid=lambda uuid: registry if uuid == registry.uuid else None,
    )
    spec = service_setup.mlflow_gateway(infra, None, SimpleNamespace(name="Gateway"))

    params = spec.params(
        {
            "registry_uuid": "registry-1",
            "requirements_txt": "numpy",
            "cache_max_models": "4",
            "cache_ttl_days": "2",
        },
        infra,
    )

    assert params["${TRACKING_URI}"] == "https://mlflow.test"
    assert params["${TRACKING_USER}"] == "mlflow"
    assert params["${TRACKING_PW}"] == "pw"
    assert params["${GATEWAY_REQUIREMENTS_TXT}"] == "numpy"
    assert params["${MODEL_REGISTRY_UUID}"] == "registry-1"


def test_gcp_setup_spec_exposes_missing_secret_manager_dependency() -> None:
    infra = SimpleNamespace(
        filter_by_group=lambda group: [],
    )

    spec = service_setup.gcp_secret_backed(
        infra,
        None,
        SimpleNamespace(name="GCP Storage"),
    )

    secret_manager = spec.fields[0]
    assert secret_manager.kind == "select"
    assert secret_manager.required is True
    assert secret_manager.options == []


def test_gcp_setup_spec_ignores_secret_managers_without_string_uuid() -> None:
    invalid_manager = SimpleNamespace(
        uuid=False,
        name="Invalid manager",
        service_config_id="openbao-docker",
    )
    valid_manager = SimpleNamespace(
        uuid="manager-1",
        name="Valid manager",
        service_config_id="openbao-docker",
    )
    infra = SimpleNamespace(
        filter_by_group=lambda group: [invalid_manager, valid_manager],
    )

    spec = service_setup.gcp_secret_backed(
        infra,
        None,
        SimpleNamespace(name="GCP Storage"),
    )

    assert spec.fields[0].options == [("Valid manager (manager-)", "manager-1")]


def test_all_builtin_service_configs_have_tui_setup_handlers() -> None:
    expected = {
        "airflow-2.9.2-docker",
        "airflow-3.1.3-docker",
        "dev-terminal-0.1-beta",
        "feast-0.54.0",
        "gcp-bigquery-0.1.0",
        "gcp-secret-manager-0.1.0",
        "gcp-sheets-0.1.0",
        "gcp-storage-0.1.0",
        "github-repo-0.1-beta-docker",
        "headlamp-newest-k3s",
        "influx-1.11.8-docker",
        "k8s-dashboard-newest-k3s",
        "kafka-3.7.0-docker",
        "kafka-4.1.0-docker",
        "kubeapps-newest-k3s",
        "kubeflow-1.10.1-k3s",
        "litellm-ollama-1.77.7-docker",
        "milvus-2.5-docker",
        "minio-release-2025-07-23-docker",
        "mlflow-2.22.0-docker",
        "mlflow-3.8.1-docker",
        "mlflow-gateway-3.8.1-docker",
        "mlflow-gateway-3.8.1-k3s",
        "mlflow-mlserver-2.22.0-docker",
        "mlflow-mlserver-3.8.1-docker",
        "mlflow-mlserver-3.8.1-k3s",
        "ollama-0.23.3-docker",
        "openbao-docker",
        "otel-0.127.0-docker",
        "otel-0.146.1-docker",
        "postgres-16-bullseye-docker",
        "redis-8-bookworm-docker",
        "registry-3-docker",
        "repo-deploy-0.1-beta-docker",
        "tsm-0.1-beta",
    }

    assert expected <= set(service_setup.SETUP_HANDLERS)
