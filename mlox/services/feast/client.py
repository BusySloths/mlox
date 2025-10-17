from __future__ import annotations

import shutil
import tempfile

from pathlib import Path
from typing import Any, Dict
from feast.repo_config import RepoConfig

from mlox.secret_manager import load_secret_manager_from_encrypted_access_keyfile


def cleanup_repo_config(tempdir: Path) -> None:
    """Remove a temporary directory created for Feast client materials."""
    shutil.rmtree(tempdir, ignore_errors=True)


def get_repo_config(
    service_name: str, encrypted_access_keyfile: str, access_password: str
) -> tuple[RepoConfig, Path]:
    """Return a RepoConfig for the remote Feast deployment along with a temp directory.

    The temporary directory contains the TLS certificates referenced by the RepoConfig.
    Callers are responsible for deleting this directory (e.g., via
    :func:`cleanup_materialized_feature_store`) once the RepoConfig is no longer needed.
    """
    sm = load_secret_manager_from_encrypted_access_keyfile(
        encrypted_access_keyfile, access_password
    )
    if not sm:
        raise RuntimeError(
            f"Failed to load secret manager from keyfile '{encrypted_access_keyfile}'."
        )
    name_uuid_map = sm.load_secret("MLOX_SERVICE_NAME_UUID_MAP")
    print(f"Loaded name_uuid_map: {name_uuid_map}")
    if (
        not name_uuid_map
        or service_name not in name_uuid_map
        or not isinstance(name_uuid_map, dict)
    ):
        raise ValueError(
            f"Service name '{service_name}' not found in secret manager name/UUID map."
        )

    service_uuid = name_uuid_map[service_name]
    # Load Feast secret
    feast_secret = sm.load_secret(service_uuid)
    if (
        not feast_secret
        or "feast_registry" not in feast_secret
        or not isinstance(feast_secret, dict)
    ):
        raise ValueError(f"Feast service secret not found for UUID '{service_uuid}'.")

    registry_secret = feast_secret["feast_registry"]
    online_uuid = registry_secret.get("online_store_uuid")
    offline_uuid = registry_secret.get("offline_store_uuid")
    if not online_uuid or not offline_uuid:
        raise ValueError("Feast service secret is missing store UUIDs.")

    online_secret = sm.load_secret(online_uuid)  # This should be a redis secret
    offline_secret = sm.load_secret(offline_uuid)  # This should be a postgres secret
    if (
        not online_secret
        or not offline_secret
        or not isinstance(online_secret, dict)
        or not isinstance(offline_secret, dict)
    ):
        raise ValueError("Feast online/offline store secrets could not be loaded.")
    online_secret = online_secret["redis_connection"]
    offline_secret = offline_secret["postgres_connection"]

    # Build repo config
    tmpdir = Path(tempfile.mkdtemp(prefix="mlox_feast_repo_"))
    try:
        # Feast Secret
        project = registry_secret["project"]
        registry_host = registry_secret["registry_host"]
        registry_port = registry_secret["registry_port"]
        registry_cert = registry_secret["certificate"]
        # Redis Secret
        redis_host = online_secret["host"]
        redis_port = online_secret["port"]
        redis_pw = online_secret["password"]
        redis_cert = online_secret["certificate"]
        # Postgres Secret
        pg_host = offline_secret["host"]
        pg_port = offline_secret["port"]
        pg_db = offline_secret["database"]
        pg_user = offline_secret["username"]
        pg_pw = offline_secret["password"]
        pg_cert = offline_secret["certificate"]

        # Write cert files
        registry_ca = tmpdir / "registry_ca.pem"
        redis_ca = tmpdir / "redis_ca.pem"
        postgres_ca = tmpdir / "postgres_ca.pem"
        registry_ca.write_text(str(registry_cert))
        redis_ca.write_text(str(redis_cert))
        postgres_ca.write_text(str(pg_cert))

        config_dict: Dict[str, Any] = {
            "project": project,
            "provider": "local",
            "registry": {
                "registry_type": "remote",
                "path": f"{registry_host}:{int(registry_port)}",
                "cert": str(registry_ca),
            },
            "online_store": {
                "type": "redis",
                "redis_type": "redis",
                "connection_string": (
                    f"{redis_host}:{int(redis_port)},ssl=True,ssl_cert_reqs=none,password={redis_pw}"
                ),
            },
            "offline_store": {
                "type": "postgres",
                "host": pg_host,
                "port": int(pg_port),
                "database": pg_db,
                "user": pg_user,
                "password": pg_pw,
                "sslmode": "require",
                "sslrootcert_path": str(postgres_ca),
            },
            "entity_key_serialization_version": 3,
            "auth": {"type": "no_auth"},
        }

        repo_config = RepoConfig(**config_dict)
        return repo_config, tmpdir
    except Exception:
        cleanup_repo_config(tmpdir)
        raise
    return None, None  # type: ignore[return-value]
