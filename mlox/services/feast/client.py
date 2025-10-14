from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

import yaml

from mlox.infra import Infrastructure
from mlox.services.feast.docker import FeastDockerService
from mlox.service import AbstractService


def _require_service(service: AbstractService | None, label: str) -> AbstractService:
    if not service:
        raise ValueError(f"Unable to locate {label} service")
    return service


def _service_host(infra: Infrastructure, service: AbstractService, label: str) -> str:
    bundle = infra.get_bundle_by_service(service)
    if bundle and bundle.server and bundle.server.ip:
        return bundle.server.ip
    raise ValueError(f"{label} service host information is unavailable")


def _service_secret(
    service: AbstractService, key: str, *, default: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    secrets = service.get_secrets() or {}
    payload = secrets.get(key, {})
    if isinstance(payload, dict):
        return payload
    if default is not None:
        return default
    return {}


def materialize_feature_store_config(
    infra: Infrastructure, service_name: str
) -> Path:
    """Create a temporary Feast client configuration for the given service.

    The returned path contains a ``feature_store.yaml`` and CA bundles for the
    registry, online (Redis) store, and offline (Postgres) store. Callers are
    responsible for removing the directory when finished.
    """

    service = infra.get_service(service_name)
    if not isinstance(service, FeastDockerService):
        raise ValueError(f"Service {service_name} is not a Feast deployment")

    tmpdir = Path(tempfile.mkdtemp(prefix="mlox_feast_remote_"))

    registry_secret = service.get_secrets().get("feast_registry", {})
    if not isinstance(registry_secret, dict):
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("Feast service did not expose registry secrets")

    registry_bundle = infra.get_bundle_by_service(service)
    registry_host = registry_secret.get("registry_host") or (
        registry_bundle.server.ip if registry_bundle else service.registry_host
    )
    registry_port = int(
        registry_secret.get("registry_port")
        or service.service_ports.get("registry", service.registry_port)
    )
    registry_cert = registry_secret.get("certificate", service.certificate)

    online_meta = service.get_secrets().get("feast_online_store", {})
    offline_meta = service.get_secrets().get("feast_offline_store", {})
    online_uuid = online_meta.get("service_uuid") or registry_secret.get(
        "online_store_uuid", ""
    )
    offline_uuid = offline_meta.get("service_uuid") or registry_secret.get(
        "offline_store_uuid", ""
    )

    redis_service = _require_service(
        infra.get_service_by_uuid(online_uuid), "Redis online store"
    )
    postgres_service = _require_service(
        infra.get_service_by_uuid(offline_uuid), "Postgres offline store"
    )

    redis_host = _service_host(infra, redis_service, "Redis online store")
    postgres_host = _service_host(infra, postgres_service, "Postgres offline store")

    redis_secret = _service_secret(redis_service, "redis_connection")
    postgres_secret = _service_secret(postgres_service, "postgres_connection")

    redis_port = int(
        redis_secret.get("port") or redis_service.service_ports.get("Redis", 0)
    )
    postgres_port = int(
        postgres_secret.get("port")
        or postgres_service.service_ports.get("Postgres", 0)
    )
    if redis_port <= 0 or postgres_port <= 0:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("Online/offline store secrets did not include ports")

    redis_password = redis_secret.get("password", "")
    postgres_database = postgres_secret.get("database", "")
    postgres_user = postgres_secret.get("username", "")
    postgres_password = postgres_secret.get("password", "")

    redis_certificate = redis_secret.get("certificate", "") or getattr(
        redis_service, "certificate", ""
    )
    postgres_certificate = postgres_secret.get("certificate", "") or getattr(
        postgres_service, "certificate", ""
    )

    registry_ca = tmpdir / "registry_ca.pem"
    redis_ca = tmpdir / "redis_ca.pem"
    postgres_ca = tmpdir / "postgres_ca.pem"

    registry_ca.write_text(registry_cert or "")
    redis_ca.write_text(redis_certificate or "")
    postgres_ca.write_text(postgres_certificate or "")

    config: Dict[str, Any] = {
        "project": registry_secret.get("project", service.project_name),
        "provider": "local",
        "registry": {
            "registry_type": "remote",
            "path": f"{registry_host}:{registry_port}",
            "ssl_cert": str(registry_ca),
        },
        "online_store": {
            "type": "redis",
            "redis_type": "redis",
            "connection_string": (
                f"rediss://:{redis_password}@{redis_host}:{redis_port}"
            ),
            "ssl": True,
            "ssl_cert": str(redis_ca),
        },
        "offline_store": {
            "type": "postgres",
            "host": postgres_host,
            "port": postgres_port,
            "database": postgres_database,
            "user": postgres_user,
            "password": postgres_password,
            "sslmode": "require",
            "sslrootcert": str(postgres_ca),
        },
        "entity_key_serialization_version": 3,
        "auth": {"type": "no_auth"},
    }

    (tmpdir / "feature_store.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    return tmpdir
