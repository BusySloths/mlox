from __future__ import annotations

import yaml
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, cast


from mlox.infra import Infrastructure
from mlox.services.feast.docker import FeastDockerService
from mlox.services.redis.docker import RedisDockerService
from mlox.services.postgres.docker import PostgresDockerService


def materialize_feature_store_config(infra: Infrastructure, service_name: str) -> Path:
    """Create a temporary Feast client configuration for the given service.

    The returned path contains a ``feature_store.yaml`` and CA bundles for the
    registry, online (Redis) store, and offline (Postgres) store. Callers are
    responsible for removing the directory when finished.
    """

    service = infra.get_service(service_name)
    if not isinstance(service, FeastDockerService):
        raise ValueError(f"Service {service_name} is not a Feast deployment")

    tmpdir = Path(tempfile.mkdtemp(prefix="mlox_feast_remote_"))

    registry_secret = service.get_secrets()["feast_registry"]
    if not isinstance(registry_secret, dict):
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("Feast service did not expose registry secrets")

    registry_bundle = infra.get_bundle_by_service(service)
    if (
        not registry_bundle
        or not registry_bundle.server
        or not registry_bundle.server.ip
    ):
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("Feast service bundle/server information is unavailable")

    registry_host = registry_bundle.server.ip
    registry_port = int(service.registry_port)
    registry_cert = service.certificate

    online_uuid = registry_secret["online_store_uuid"]
    offline_uuid = registry_secret["offline_store_uuid"]

    redis_service = infra.get_service_by_uuid(online_uuid)
    postgres_service = infra.get_service_by_uuid(offline_uuid)
    if not redis_service or not postgres_service:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError("Feast online/offline store services are unavailable")
    redis_service = cast(RedisDockerService, redis_service)
    postgres_service = cast(PostgresDockerService, postgres_service)

    online_bundle = infra.get_bundle_by_service(redis_service)
    offline_bundle = infra.get_bundle_by_service(postgres_service)
    if not online_bundle or not offline_bundle:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise ValueError(
            "Feast online/offline store bundle/server information is unavailable"
        )
    redis_host = online_bundle.server.ip
    postgres_host = offline_bundle.server.ip

    registry_ca = tmpdir / "registry_ca.pem"
    redis_ca = tmpdir / "redis_ca.pem"
    postgres_ca = tmpdir / "postgres_ca.pem"

    registry_ca.write_text(registry_cert)
    redis_ca.write_text(redis_service.certificate)
    postgres_ca.write_text(postgres_service.certificate)

    config: Dict[str, Any] = {
        "project": registry_secret.get("project", service.project_name),
        "provider": "local",
        "registry": {
            "registry_type": "remote",
            "path": f"{registry_host}:{registry_port}",
            "cert": str(registry_ca),
        },
        "online_store": {
            "type": "redis",
            # "redis_type": "redis",
            "connection_string": (
                # f"rediss://:{redis_service.pw}@{redis_host}:{redis_service.port}"
                f"{redis_host}:{redis_service.port},ssl=True,password={redis_service.pw}"
            ),
            # "ssl": True,
            # "ssl_cert": str(redis_ca),
        },
        "offline_store": {
            "type": "postgres",
            "host": postgres_host,
            "port": postgres_service.port,
            "database": postgres_service.db,
            "user": postgres_service.user,
            "password": postgres_service.pw,
            # "sslmode": "require",
            # "sslrootcert": str(postgres_ca),
        },
        "entity_key_serialization_version": 3,
        "auth": {"type": "no_auth"},
    }

    (tmpdir / "feature_store.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    return tmpdir
