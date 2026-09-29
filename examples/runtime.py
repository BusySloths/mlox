"""Optional provider discovery shared by the runnable examples."""
import logging
import os

from mlox.secret_manager import (
    SECRET_MANAGER_KEYFILE_ENV, SECRET_MANAGER_KEYFILE_PW_ENV,
    load_secret_manager_from_env,
)
from mlox.service import AbstractObservabilityService, AbstractSecretManagerService
from mlox.services.otel.client import OTelClient, set_telemetry_client

logger = logging.getLogger(__name__)


def setup_runtime(*, tracking=False):
    """Prefer environment settings; optionally discover running project services."""
    workspace = None
    project = os.environ.get("MLOX_PROJECT_PATH")
    password = os.environ.get("MLOX_PROJECT_PASSWORD")
    if bool(project) != bool(password):
        raise ValueError("Set both MLOX_PROJECT_PATH and MLOX_PROJECT_PASSWORD.")
    if project:
        from examples.load_project_data import load_project_workspace
        workspace = load_project_workspace()
    services = [s for b in (workspace.infrastructure.bundles if workspace else [])
                for s in b.services if s.state == "running"]

    def select(candidates, selector):
        requested = os.environ.get(selector)
        if requested:
            candidates = [s for s in candidates if requested in (s.name, s.service_uuid)]
            if not candidates:
                raise ValueError(f"No running provider matches {selector}.")
        if len(candidates) > 1:
            raise ValueError(f"Multiple providers found; set {selector} to a name or UUID.")
        if candidates:
            service = candidates[0]
            logger.info("%s: found %s (%s)", selector, service.name, service.service_uuid)
            return service
        return None

    for capability, selector, keys, method in (
        (AbstractObservabilityService, "MLOX_EXAMPLE_TELEMETRY",
         ("OTEL_EXPORTER_OTLP_ENDPOINT",), "get_telemetry_env_binding"),
        (AbstractSecretManagerService, "MLOX_EXAMPLE_SECRET_MANAGER",
         (SECRET_MANAGER_KEYFILE_ENV, SECRET_MANAGER_KEYFILE_PW_ENV),
         "get_secret_manager_env_binding"),
    ):
        if os.environ.get(selector, "").lower() == "none":
            for key in keys:
                os.environ.pop(key, None)
            logger.info("%s: disabled", selector)
        elif any(os.environ.get(key) for key in keys):
            if not all(os.environ.get(key) for key in keys):
                raise ValueError(f"Incomplete configuration for {selector}.")
            logger.info("%s: found environment configuration", selector)
        else:
            provider = select([s for s in services if isinstance(s, capability)], selector)
            if provider:
                os.environ.update(getattr(provider, method)())
            else:
                logger.info("%s: not found (optional)", selector)

    if tracking:
        uri = os.environ.get("MLFLOW_URI") or os.environ.get("MLFLOW_TRACKING_URI")
        if not uri:
            candidates = (workspace.infrastructure.filter_by_group("experiment-tracking")
                          if workspace else [])
            tracker = select([s for s in candidates if s.state == "running"], "MLOX_EXAMPLE_TRACKER")
            if tracker:
                secret = tracker.get_secrets()
                uri = secret["service_url"]
                os.environ["MLFLOW_TRACKING_USERNAME"] = str(secret.get("username", ""))
                os.environ["MLFLOW_TRACKING_PASSWORD"] = str(secret.get("password", ""))
                os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = str(secret.get("insecure_tls", "false")).lower()
            else:
                uri = "sqlite:///mlox-example-mlflow.db"
                logger.info("MLflow: using local SQLite tracking")
        else:
            logger.info("MLflow: found environment configuration")
        os.environ["MLFLOW_URI"] = uri

    manager = load_secret_manager_from_env() if os.environ.get(SECRET_MANAGER_KEYFILE_ENV) else None
    client = OTelClient.from_env(resource_attrs={"service.name": "mlox.examples"})
    set_telemetry_client(client)
    logger.info("Runtime clients: telemetry=%s, secret_manager=%s", client is not None, manager is not None)
    return client, manager
