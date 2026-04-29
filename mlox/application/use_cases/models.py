from __future__ import annotations

from typing import Dict, Optional

from mlox.application.result import OperationResult


def list_models(
    load_session,
    project: str,
    password: str,
    *,
    registry_name: Optional[str] = None,
) -> OperationResult:
    result = load_session(project, password)
    if not result.success:
        return result

    session = result.data
    model_servers = session.infra.filter_by_group("model-server")
    registries = session.infra.filter_by_group("model-registry")
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


def deploy_model(
    load_session,
    add_service,
    setup_service,
    project: str,
    password: str,
    *,
    registry_name: Optional[str],
    model_name: str,
    model_version: str,
    server_ip: str,
    template_id: str,
) -> OperationResult:
    result = load_session(project, password)
    if not result.success:
        return result

    session = result.data
    target_bundle = session.infra.get_bundle_by_ip(server_ip)
    if not target_bundle:
        return OperationResult(False, 14, f"Server {server_ip} not found in infrastructure.")

    registries = session.infra.filter_by_group("model-registry")
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
        project=project,
        password=password,
        server_ip=server_ip,
        template_id=template_id,
        params=params,
    )
    if not add_result.success:
        return add_result
    if not add_result.data or "service" not in add_result.data:
        return OperationResult(False, 15, "Failed to retrieve deployed service.")

    service = add_result.data["service"]
    return setup_service(project=project, password=password, name=service.name)
