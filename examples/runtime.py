"""Project-based provider setup shared by the runnable examples."""
import logging
import os

from examples.load_project_data import load_project_workspace
from mlox.secret_manager import (
    SECRET_MANAGER_KEYFILE_ENV, SECRET_MANAGER_KEYFILE_PW_ENV,
    load_secret_manager_from_env,
)
from mlox.service import AbstractObservabilityService, AbstractSecretManagerService
from mlox.services.otel.client import OTelClient, set_telemetry_client

logger = logging.getLogger(__name__)


def setup_runtime(*, tracking=False):
    """Use the first running providers in the configured MLOX project."""
    workspace = load_project_workspace()
    services = [s for b in workspace.infrastructure.bundles
                for s in b.services if s.state == "running"]

    def first(candidates, label):
        if not candidates:
            logger.info("%s: not found", label)
            return None
        service = candidates[0]
        bundle = workspace.infrastructure.get_bundle_by_service(service)
        server = bundle.server if bundle else None
        logger.info(
            "%s: selected %s (%s), server=%s (%s)",
            label, service.name, service.service_uuid,
            getattr(server, "name", None) or getattr(server, "uuid", "unknown"),
            getattr(server, "ip", "unknown"),
        )
        return service

    if tracking:
        tracker = first(
            [s for s in workspace.infrastructure.filter_by_group("experiment-tracking")
             if s.state == "running"], "MLflow",
        )
        if tracker is None:
            raise RuntimeError("The tracking example requires a running MLflow service.")
        secret = tracker.get_secrets()
        os.environ["MLFLOW_URI"] = str(secret["service_url"])
        os.environ["MLFLOW_TRACKING_USERNAME"] = str(secret.get("username", ""))
        os.environ["MLFLOW_TRACKING_PASSWORD"] = str(secret.get("password", ""))
        os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = str(secret.get("insecure_tls", "false")).lower()

    # These examples use project providers, not inherited runtime bindings.
    for key in (SECRET_MANAGER_KEYFILE_ENV, SECRET_MANAGER_KEYFILE_PW_ENV):
        os.environ.pop(key, None)
    manager_provider = first(
        [s for s in services if isinstance(s, AbstractSecretManagerService)],
        "Secret manager",
    )
    manager = None
    if manager_provider:
        os.environ.update(manager_provider.get_secret_manager_env_binding())
        manager = load_secret_manager_from_env()

    telemetry_provider = first(
        [s for s in services if isinstance(s, AbstractObservabilityService)],
        "Telemetry",
    )
    client = None
    if telemetry_provider:
        client = OTelClient.from_env(
            environ=telemetry_provider.get_telemetry_env_binding(),
            resource_attrs={"service.name": "mlox.examples"},
        )
    set_telemetry_client(client)
    logger.info("Runtime clients: telemetry=%s, secret_manager=%s",
                client is not None, manager is not None)
    return client, manager
