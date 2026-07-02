from __future__ import annotations

import json
import shlex
from typing import Any, Dict, Optional

import requests
import urllib3

from mlox.application.result import OperationResult
from mlox.project.state import WorkspaceState


STANDALONE_REGISTRY_ID = "__standalone__"


def describe_model_operations(infra) -> OperationResult:
    """Return registries, connected endpoints, and supported models."""

    registries = _collect_registries(infra)
    endpoints = _collect_model_endpoints(infra, registries)
    models_by_endpoint: dict[str, list[dict[str, Any]]] = {}
    for endpoint in endpoints:
        service = endpoint["service_ref"]
        endpoint_id = str(endpoint["id"])
        try:
            models = list(service.list_supported_models())
        except Exception as exc:
            models = [
                {
                    "name": "Unavailable",
                    "version": "-",
                    "type": endpoint["type"],
                    "status": f"Error: {exc}",
                    "model_uri": "-",
                }
            ]
        models_by_endpoint[endpoint_id] = models

    return OperationResult(
        True,
        0,
        "Model operations loaded.",
        {
            "registries": registries,
            "endpoints": endpoints,
            "models_by_endpoint": models_by_endpoint,
        },
    )


def build_model_example(
    endpoint: dict[str, Any],
    model: dict[str, Any] | None = None,
) -> OperationResult:
    """Build one concrete serving example for a selected endpoint/model."""

    service = endpoint.get("service_ref")
    if service is None:
        return OperationResult(False, 40, "Model endpoint service is unavailable.")
    try:
        example = _service_example(service, model, _model_input_example(service, model))
    except Exception as exc:
        return OperationResult(False, 41, f"Could not build example: {exc}")
    return OperationResult(True, 0, "Model example loaded.", {"example": example})


def call_model_example(example: str, *, timeout: int = 60) -> OperationResult:
    """Execute a generated curl example and return the response text."""

    try:
        request = _parse_curl_example(example)
    except ValueError as exc:
        return OperationResult(False, 42, str(exc))
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(
            request["url"],
            headers=request["headers"],
            data=request["body"],
            auth=request["auth"],
            verify=False,
            timeout=timeout,
        )
    except Exception as exc:
        return OperationResult(False, 43, f"Model call failed: {exc}")

    body = response.text
    try:
        body = json.dumps(response.json(), indent=2, sort_keys=True)
    except ValueError:
        pass
    return OperationResult(
        200 <= response.status_code < 300,
        0 if 200 <= response.status_code < 300 else response.status_code,
        f"HTTP {response.status_code}",
        {"status_code": response.status_code, "body": body},
    )


def list_models(
    project: WorkspaceState,
    *,
    registry_name: Optional[str] = None,
) -> OperationResult:
    model_servers = project.infrastructure.filter_by_group("model-server")
    registries = project.infrastructure.filter_by_group("model-registry")
    if not registries:
        return OperationResult(False, 11, "No model registry service found in the project.")

    if registry_name:
        registries = [service for service in registries if service.name == registry_name]
        if not registries:
            return OperationResult(
                False,
                13,
                f"Registry service '{registry_name}' not found in the project.",
            )

    models = []
    for registry in registries:
        for model in registry.list_models():
            is_deployed = False
            for server in model_servers:
                if not hasattr(server, "is_model"):
                    continue
                model_key = (
                    f"{registry.name}:{model.get('Model', '')}:{model.get('Version', '')}"
                )
                is_deployed = server.is_model(model_key)
                if is_deployed:
                    break

            model["registry_name"] = registry.name
            model["is_deployed"] = is_deployed
            models.append(model)

    message = "No registered models found." if not models else "Registered models retrieved."
    return OperationResult(True, 0, message, {"models": models})


def _parse_curl_example(example: str) -> dict[str, Any]:
    command = example.replace("\\\n", " ").strip()
    parts = shlex.split(command)
    if not parts or parts[0] != "curl":
        raise ValueError("Load a curl serving example before calling the model.")
    headers: dict[str, str] = {}
    body = ""
    auth: tuple[str, str] | None = None
    url = ""
    index = 1
    while index < len(parts):
        part = parts[index]
        if part in {"-k", "--insecure"}:
            index += 1
            continue
        if part in {"-u", "--user"}:
            index += 1
            user_password = parts[index]
            user, _, password = user_password.partition(":")
            auth = (user, password)
        elif part in {"-H", "--header"}:
            index += 1
            name, _, value = parts[index].partition(":")
            if name and value:
                headers[name.strip()] = value.strip()
        elif part in {"-d", "--data", "--data-raw", "--data-binary"}:
            index += 1
            body = parts[index]
        elif part.startswith("http://") or part.startswith("https://"):
            url = part
        index += 1
    if not url:
        raise ValueError("The curl example does not contain an endpoint URL.")
    return {"url": url, "headers": headers, "body": body, "auth": auth}


def deploy_model(
    project: WorkspaceState,
    add_service,
    setup_service,
    *,
    registry_name: Optional[str],
    model_name: str,
    model_version: str,
    server_ip: str,
    template_id: str,
) -> OperationResult:
    target_bundle = project.infrastructure.get_bundle_by_ip(server_ip)
    if not target_bundle:
        return OperationResult(False, 14, f"Server {server_ip} not found in infrastructure.")

    registries = project.infrastructure.filter_by_group("model-registry")
    registry_service = next(
        (service for service in registries if service.name == registry_name),
        None,
    )
    if not registry_service:
        return OperationResult(False, 11, "No MLflow registry service found in the project.")

    secrets = registry_service.get_secrets()
    params: Dict[str, str] = {
        "${MODEL_NAME}": f"{model_name}/{model_version}",
        "${TRACKING_URI}": str(secrets.get("service_url", "")),
        "${TRACKING_USER}": str(secrets.get("username", "")),
        "${TRACKING_PW}": str(secrets.get("password", "")),
    }

    add_result = add_service(
        project,
        server_ip=server_ip,
        template_id=template_id,
        params=params,
    )
    if not add_result.success:
        return add_result
    if not add_result.data or "service" not in add_result.data:
        return OperationResult(False, 15, "Failed to retrieve deployed service.")

    service = add_result.data["service"]
    return setup_service(project, name=service.name)


def _collect_registries(infra) -> list[dict[str, Any]]:
    registries = []
    for service in _filter_by_group(infra, "model-registry"):
        bundle = _get_bundle_by_service(infra, service)
        registries.append(
            {
                "id": str(getattr(service, "uuid", getattr(service, "name", ""))),
                "name": str(getattr(service, "name", "-")),
                "location": _service_location(bundle),
                "type": str(getattr(service, "service_config_id", "registry")),
                "status": str(getattr(service, "state", "unknown")),
            }
        )
    standalone = _standalone_model_servers(infra)
    if standalone:
        registries.append(
            {
                "id": STANDALONE_REGISTRY_ID,
                "name": "Standalone Endpoints",
                "location": "No model registry",
                "type": "standalone",
                "status": str(len(standalone)),
            }
        )
    return registries


def _collect_model_endpoints(
    infra,
    registries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    registry_ids = {row["id"] for row in registries}
    endpoints = []
    for service in _filter_by_group(infra, "model-server"):
        bundle = _get_bundle_by_service(infra, service)
        registry = _endpoint_registry(service)
        registry_id = str(getattr(registry, "uuid", "") or STANDALONE_REGISTRY_ID)
        if registry_id not in registry_ids:
            registry_id = STANDALONE_REGISTRY_ID
        endpoints.append(
            {
                "id": str(getattr(service, "uuid", getattr(service, "name", ""))),
                "registry_id": registry_id,
                "name": str(getattr(service, "name", "-")),
                "bundle": str(getattr(bundle, "name", "-")) if bundle else "-",
                "location": _service_location(bundle),
                "type": str(getattr(service, "service_config_id", "model-server")),
                "status": str(getattr(service, "state", "unknown")),
                "url": _primary_url(service),
                "service_ref": service,
            }
        )
    return endpoints


def _standalone_model_servers(infra) -> list:
    servers = []
    for service in _filter_by_group(infra, "model-server"):
        if _endpoint_registry(service) is None:
            servers.append(service)
    return servers


def _filter_by_group(infra, group: str) -> list:
    filter_by_group = getattr(infra, "filter_by_group", None)
    if callable(filter_by_group):
        return list(filter_by_group(group))
    services = []
    expected = group.replace("-", "_")
    for bundle in getattr(infra, "bundles", []) or []:
        for service in getattr(bundle, "services", []) or []:
            capabilities = getattr(service, "capabilities", set()) or set()
            capability_values = {
                capability.value if hasattr(capability, "value") else str(capability)
                for capability in capabilities
            }
            if expected in capability_values or group in capability_values:
                services.append(service)
    return services


def _get_bundle_by_service(infra, service):
    get_bundle_by_service = getattr(infra, "get_bundle_by_service", None)
    if callable(get_bundle_by_service):
        return get_bundle_by_service(service)
    for bundle in getattr(infra, "bundles", []) or []:
        if service in (getattr(bundle, "services", []) or []):
            return bundle
    return None


def _endpoint_registry(service):
    get_registry = getattr(service, "get_registry", None)
    if not callable(get_registry):
        return None
    try:
        return get_registry()
    except Exception:
        return None


def _model_input_example(service, model: dict[str, Any] | None) -> Any | None:
    if not model:
        return None
    registry = _endpoint_registry(service)
    load_artifact = getattr(registry, "load_artifact", None)
    if not callable(load_artifact):
        return None
    model_name = str(model.get("name") or "")
    model_version = str(model.get("version") or "")
    if not model_name or not model_version or model_version == "-":
        return None
    return load_artifact(model_name, model_version, "input_example.json")


def _service_example(service, model, input_example: Any | None) -> str:
    return service.get_example(model, input_example=input_example)


def _service_location(bundle) -> str:
    if not bundle:
        return "-"
    server = getattr(bundle, "server", None)
    return f"{getattr(bundle, 'name', '-')} / {getattr(server, 'ip', '-')}"


def _primary_url(service) -> str:
    service_url = str(getattr(service, "service_url", "") or "")
    if service_url:
        return service_url
    urls = getattr(service, "service_urls", {}) or {}
    return str(next(iter(urls.values()), ""))
