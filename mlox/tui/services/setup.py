"""TUI setup forms for service templates."""

from __future__ import annotations

from typing import Any

from mlox.service import ServiceCapability
from mlox.tui.template_forms import TemplateFieldSpec, TemplateFormSpec


def no_params(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title=f"Add {getattr(config, 'name', 'Service')}",
        description="This service does not need additional parameters before adding.",
        fields=[],
        submit_label="Add Service",
        materialize=lambda values, infra: {},
    )


def github_repo(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add GitHub Repository",
        description="Add a repository service to this bundle. Setup/clone runs later.",
        fields=[
            TemplateFieldSpec("owner", "User or organization"),
            TemplateFieldSpec("repo", "Repository name"),
            TemplateFieldSpec(
                "private",
                "Repository visibility",
                kind="select",
                default="false",
                options=[("Public", "false"), ("Private", "true")],
            ),
        ],
        submit_label="Add Service",
        materialize=_materialize_github,
    )


def postgres(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add Postgres",
        fields=[
            TemplateFieldSpec("database", "Database name", default="mlox"),
        ],
        submit_label="Add Service",
        materialize=lambda values, infra: {"${POSTGRES_DB}": values["database"]},
    )


def gcp_secret_backed(infra, bundle, config=None) -> TemplateFormSpec:
    managers = _service_options(infra, group="secret-manager")
    return TemplateFormSpec(
        title=f"Add {getattr(config, 'name', 'GCP Service')}",
        description=(
            "Select the secret manager and key that already contains the GCP "
            "service-account JSON."
        ),
        fields=[
            TemplateFieldSpec(
                "secret_manager_uuid",
                "Secret manager",
                kind="select",
                options=managers,
            ),
            TemplateFieldSpec("secret_name", "Secret name"),
        ],
        submit_label="Add Service",
        materialize=lambda values, infra: {
            "${SECRET_MANAGER_UUID}": values["secret_manager_uuid"],
            "${SECRET_NAME}": values["secret_name"],
        },
    )


def feast(infra, bundle, config=None) -> TemplateFormSpec:
    redis = _service_options(infra, config_prefix="redis-")
    postgres_services = _service_options(infra, config_prefix="postgres-")
    return TemplateFormSpec(
        title="Add Feast Feature Store",
        description="Feast needs existing Redis and Postgres services.",
        fields=[
            TemplateFieldSpec(
                "project_name",
                "Feast project name",
                default="feast_project",
            ),
            TemplateFieldSpec(
                "online_store_uuid",
                "Online store (Redis)",
                kind="select",
                options=redis,
            ),
            TemplateFieldSpec(
                "offline_store_uuid",
                "Offline store (Postgres)",
                kind="select",
                options=postgres_services,
            ),
        ],
        submit_label="Add Service",
        materialize=lambda values, infra: {
            "${FEAST_PROJECT_NAME}": values["project_name"],
            "${ONLINE_STORE_UUID}": values["online_store_uuid"],
            "${OFFLINE_STORE_UUID}": values["offline_store_uuid"],
        },
    )


def litellm(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add LiteLLM + Ollama",
        fields=[
            TemplateFieldSpec(
                "openai_key",
                "OpenAI key",
                kind="password",
                required=False,
            ),
            TemplateFieldSpec(
                "ollama_models",
                "Ollama models",
                default="llama3.2:1b",
                help="Comma-separated model names.",
            ),
        ],
        submit_label="Add Service",
        materialize=lambda values, infra: {
            "${OPENAI_KEY}": values.get("openai_key", ""),
            "${OLLAMA_MODELS}": _csv(values.get("ollama_models", "")),
        },
    )


def ollama(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add Ollama",
        fields=[
            TemplateFieldSpec(
                "ollama_models",
                "Ollama models",
                default="llama3.2:1b",
                help="Comma-separated model names.",
            ),
        ],
        submit_label="Add Service",
        materialize=lambda values, infra: {
            "${OLLAMA_MODELS}": _csv(values.get("ollama_models", "")),
        },
    )


def mlflow_mlserver(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add MLflow MLServer",
        description="Select a registry and enter the model URI/version to serve.",
        fields=[
            TemplateFieldSpec(
                "registry_uuid",
                "Model registry",
                kind="select",
                options=_model_registry_options(infra),
            ),
            TemplateFieldSpec(
                "model_uri",
                "Model URI",
                placeholder="models:/name/version",
            ),
        ],
        submit_label="Add Service",
        materialize=_materialize_mlserver,
    )


def mlflow_gateway(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add MLflow Gateway",
        description="Select a registry and optional runtime/cache settings.",
        fields=[
            TemplateFieldSpec(
                "registry_uuid",
                "Model registry",
                kind="select",
                options=_model_registry_options(infra),
            ),
            TemplateFieldSpec(
                "requirements_txt",
                "Additional requirements.txt",
                kind="multiline",
                required=False,
            ),
            TemplateFieldSpec(
                "cache_max_models",
                "Max cached models",
                kind="integer",
                default="10",
                min_value=1,
            ),
            TemplateFieldSpec(
                "cache_ttl_days",
                "Cache TTL days",
                default="10",
            ),
        ],
        submit_label="Add Service",
        materialize=_materialize_gateway,
    )


def otel(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add OpenTelemetry Collector",
        fields=[
            TemplateFieldSpec("relic_key", "New Relic OTLP key", required=False),
            TemplateFieldSpec(
                "relic_endpoint",
                "New Relic OTLP endpoint",
                default="https://otlp.eu01.nr-data.net:4317",
                required=False,
            ),
            TemplateFieldSpec(
                "grafana_cloud_key",
                "Grafana Cloud authorization header",
                required=False,
            ),
            TemplateFieldSpec(
                "grafana_cloud_endpoint",
                "Grafana Cloud OTLP endpoint",
                required=False,
            ),
        ],
        submit_label="Add Service",
        materialize=lambda values, infra: {
            "${MLOX_RELIC_KEY}": values.get("relic_key", ""),
            "${MLOX_RELIC_ENDPOINT}": values.get("relic_endpoint", ""),
            "${MLOX_GRAFANA_CLOUD_KEY}": values.get("grafana_cloud_key", ""),
            "${MLOX_GRAFANA_CLOUD_ENDPOINT}": values.get(
                "grafana_cloud_endpoint", ""
            ),
        },
    )


def repo_deploy(infra, bundle, config=None) -> TemplateFormSpec:
    return TemplateFormSpec(
        title="Add Repository Docker Deploy",
        description=(
            "Select an existing repository service and enter the compose file "
            "path relative to the repository root."
        ),
        fields=[
            TemplateFieldSpec(
                "repo_uuid",
                "Repository service",
                kind="select",
                options=_service_options(infra, group="repository"),
            ),
            TemplateFieldSpec(
                "compose_file",
                "Compose file",
                placeholder="docker-compose.yaml",
            ),
            TemplateFieldSpec(
                "deployment_name",
                "Deployment name",
                default="repo-deploy",
            ),
        ],
        submit_label="Add Service",
        materialize=lambda values, infra: {
            "${REPO_DEPLOY_NAME}": values["deployment_name"],
            "${REPO_DEPLOY_REPO_UUID}": values["repo_uuid"],
            "${REPO_DEPLOY_COMPOSE_FILE}": values["compose_file"],
        },
    )


def _materialize_github(values: dict[str, str], infra) -> dict[str, str]:
    owner = values["owner"].strip()
    repo = values["repo"].strip()
    is_private = values.get("private") == "true"
    link = (
        f"git@github.com:{owner}/{repo}.git"
        if is_private
        else f"https://github.com/{owner}/{repo}.git"
    )
    return {
        "${GITHUB_LINK}": link,
        "${GITHUB_NAME}": repo,
        "${GITHUB_PRIVATE}": str(is_private),
    }


def _materialize_mlserver(values: dict[str, str], infra) -> dict[str, str]:
    registry = _service_by_uuid(infra, values["registry_uuid"])
    secrets = _registry_secrets(registry)
    return {
        "${MODEL_NAME}": values["model_uri"],
        "${TRACKING_URI}": secrets.get("service_url", ""),
        "${TRACKING_USER}": secrets.get("username", ""),
        "${TRACKING_PW}": secrets.get("password", ""),
        "${MODEL_REGISTRY_UUID}": values["registry_uuid"],
    }


def _materialize_gateway(values: dict[str, str], infra) -> dict[str, str]:
    registry = _service_by_uuid(infra, values["registry_uuid"])
    secrets = _registry_secrets(registry)
    return {
        "${TRACKING_URI}": secrets.get("service_url", ""),
        "${TRACKING_USER}": secrets.get("username", ""),
        "${TRACKING_PW}": secrets.get("password", ""),
        "${GATEWAY_REQUIREMENTS_TXT}": values.get("requirements_txt", ""),
        "${GATEWAY_CACHE_MAX_MODELS}": values.get("cache_max_models", "10"),
        "${GATEWAY_CACHE_TTL_DAYS}": values.get("cache_ttl_days", "10"),
        "${MODEL_REGISTRY_UUID}": values["registry_uuid"],
    }


def _model_registry_options(infra) -> list[tuple[str, str]]:
    return _service_options(infra, capability=ServiceCapability.MODEL_REGISTRY.value)


def _service_options(
    infra,
    *,
    group: str | None = None,
    capability: str | None = None,
    config_prefix: str | None = None,
) -> list[tuple[str, str]]:
    services = list(_iter_services(infra))
    if group and hasattr(infra, "filter_by_group"):
        try:
            services = list(infra.filter_by_group(group))
        except Exception:
            services = []
    if capability:
        services = [
            service
            for service in services
            if capability in _capability_names(service)
        ]
    if config_prefix:
        services = [
            service
            for service in services
            if str(getattr(service, "service_config_id", "")).startswith(config_prefix)
        ]
    options: list[tuple[str, str]] = []
    for service in services:
        service_uuid = getattr(service, "uuid", "")
        if not isinstance(service_uuid, str) or not service_uuid:
            continue
        options.append((f"{service.name} ({service_uuid[:8]})", service_uuid))
    return options


def _iter_services(infra):
    if not infra:
        return []
    services = getattr(infra, "services", None)
    if callable(services):
        return list(services())
    return [
        service
        for bundle in getattr(infra, "bundles", []) or []
        for service in getattr(bundle, "services", []) or []
    ]


def _service_by_uuid(infra, service_uuid: str):
    getter = getattr(infra, "get_service_by_uuid", None)
    if callable(getter):
        return getter(service_uuid)
    for service in _iter_services(infra):
        if getattr(service, "uuid", None) == service_uuid:
            return service
    return None


def _registry_secrets(registry) -> dict[str, Any]:
    get_secrets = getattr(registry, "get_secrets", None)
    if not callable(get_secrets):
        return {}
    secrets = get_secrets() or {}
    if "service_url" in secrets:
        return secrets
    for value in secrets.values():
        if isinstance(value, dict) and "service_url" in value:
            return value
    return {}


def _capability_names(service) -> set[str]:
    return {
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in getattr(service, "capabilities", set()) or []
    }


def _csv(value: str) -> str:
    return ",".join(item.strip() for item in value.split(",") if item.strip())


SETUP_HANDLERS = {
    "airflow-2.9.2-docker": no_params,
    "airflow-3.1.3-docker": no_params,
    "dev-terminal-0.1-beta": no_params,
    "feast-0.54.0": feast,
    "gcp-bigquery-0.1.0": gcp_secret_backed,
    "gcp-secret-manager-0.1.0": gcp_secret_backed,
    "gcp-sheets-0.1.0": gcp_secret_backed,
    "gcp-storage-0.1.0": gcp_secret_backed,
    "github-repo-0.1-beta-docker": github_repo,
    "headlamp-newest-k3s": no_params,
    "influx-1.11.8-docker": no_params,
    "k8s-dashboard-newest-k3s": no_params,
    "kafka-3.7.0-docker": no_params,
    "kafka-4.1.0-docker": no_params,
    "kubeapps-newest-k3s": no_params,
    "kubeflow-1.10.1-k3s": no_params,
    "litellm-ollama-1.77.7-docker": litellm,
    "milvus-2.5-docker": no_params,
    "minio-release-2025-07-23-docker": no_params,
    "mlflow-2.22.0-docker": no_params,
    "mlflow-3.8.1-docker": no_params,
    "mlflow-gateway-3.8.1-docker": mlflow_gateway,
    "mlflow-gateway-3.8.1-k3s": mlflow_gateway,
    "mlflow-mlserver-2.22.0-docker": mlflow_mlserver,
    "mlflow-mlserver-3.8.1-docker": mlflow_mlserver,
    "mlflow-mlserver-3.8.1-k3s": mlflow_mlserver,
    "ollama-0.23.3-docker": ollama,
    "openbao-docker": no_params,
    "otel-0.127.0-docker": otel,
    "otel-0.146.1-docker": otel,
    "postgres-16-bullseye-docker": postgres,
    "redis-8-bookworm-docker": no_params,
    "registry-3-docker": no_params,
    "repo-deploy-0.1-beta-docker": repo_deploy,
    "tsm-0.1-beta": no_params,
}
