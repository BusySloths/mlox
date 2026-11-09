"""Virtual MLOX connector for an existing PostgreSQL/S3 DuckLake."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mlox.service import AbstractService, ServiceCapability

if TYPE_CHECKING:
    from mlox.infra import Infrastructure
    from mlox.services.ducklake.client import DuckLakeClient


@dataclass
class DuckLakeService(AbstractService):
    capabilities = {ServiceCapability.DATA_WAREHOUSE}
    postgres_service_uuid: str
    storage_service_uuid: str
    data_path: str
    metadata_schema: str = "ducklake"
    catalog_name: str = "lake"
    # Kept for connectors configured before service secret collection.
    secret_manager_uuid: str = ""
    postgres_secret_name: str = ""
    s3_secret_name: str = ""

    def _dependencies(self, infra):
        dependencies = {}
        for role, uuid, capability in (
            ("PostgreSQL", self.postgres_service_uuid, ServiceCapability.DATABASE),
            ("object storage", self.storage_service_uuid, ServiceCapability.S3_OBJECT_STORAGE),
        ):
            service = infra.get_service_by_uuid(uuid)
            if service is None or capability not in getattr(service, "capabilities", set()):
                raise ValueError(f"Configured {role} service is missing or incompatible")
            dependencies[role] = service
        return dependencies

    def get_client(self, infra: Infrastructure) -> DuckLakeClient:
        from mlox.services.ducklake.client import DuckLakeClient

        if not self.postgres_secret_name and not self.s3_secret_name:
            self._dependencies(infra)
            return DuckLakeClient(_LiveServiceSecrets(self, infra), self.uuid, self.uuid,
                                  self.data_path, self.metadata_schema, self.catalog_name)
        dependencies = self._dependencies(infra)
        manager_service = infra.get_service_by_uuid(self.secret_manager_uuid)
        get_manager = getattr(manager_service, "get_secret_manager", None)
        if not callable(get_manager):
            raise ValueError("Configured secret manager service is missing or incompatible")
        manager = get_manager(infra)
        if manager is None:
            raise ValueError("Could not initialize configured secret manager")
        pg = dependencies["PostgreSQL"]
        storage = dependencies["object storage"]
        pg_urls = getattr(pg, "service_urls", {}) or {}
        storage_urls = getattr(storage, "service_urls", {}) or {}
        postgres_defaults = {
            "host": pg_urls.get("Postgres IP", ""),
            "port": getattr(pg, "port", 5432),
            "database": getattr(pg, "db", ""),
        }
        s3_defaults = {"endpoint": storage_urls.get("MinIO API", "") or getattr(storage, "service_url", "")}
        return DuckLakeClient(manager, self.postgres_secret_name or self.uuid, self.s3_secret_name or self.uuid,
                              self.data_path, self.metadata_schema, self.catalog_name,
                              postgres_defaults=postgres_defaults, s3_defaults=s3_defaults)

    def setup(self, conn) -> None:
        self.state = "running"

    def _connection_secret(self, infra) -> dict:
        dependencies = self._dependencies(infra)
        pg_service = dependencies["PostgreSQL"]
        storage = dependencies["object storage"]
        pg = pg_service.get_secrets().get("postgres_connection", {})
        storage_secrets = storage.get_secrets()
        s3 = storage_secrets.get("s3_connection") or storage_secrets.get("minio_root_credentials", {})
        if not isinstance(pg, dict) or not isinstance(s3, dict):
            raise ValueError("Selected services must export connection secrets")
        pg_urls = getattr(pg_service, "service_urls", {}) or {}
        storage_urls = getattr(storage, "service_urls", {}) or {}
        pg = {"host": pg_urls.get("Postgres IP", ""), "port": getattr(pg_service, "port", 5432),
              "database": getattr(pg_service, "db", ""), **pg}
        s3 = {"endpoint": storage_urls.get("MinIO API", "") or getattr(storage, "service_url", ""), **s3}
        for label, value in (("PostgreSQL host", pg.get("host")), ("PostgreSQL database", pg.get("database")),
                             ("PostgreSQL username", pg.get("username")), ("PostgreSQL password", pg.get("password")),
                             ("S3 endpoint", s3.get("endpoint")), ("S3 access key", s3.get("access_key") or s3.get("access_key_id") or s3.get("username")),
                             ("S3 secret key", s3.get("secret_key") or s3.get("secret_access_key") or s3.get("password"))):
            if not value:
                raise ValueError(f"Selected service did not export {label}")
        return {
            "ducklake_connection": {"catalog_name": self.catalog_name, "metadata_schema": self.metadata_schema,
                                    "data_path": self.data_path, "service_uuid": self.uuid},
            "postgres_connection": pg,
            "s3_connection": s3,
        }

    def teardown(self, conn) -> None:
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        self.state = "running"
        return True

    def spin_down(self, conn) -> bool:
        self.state = "stopped"
        return True

    def check(self, conn) -> dict[str, str]:
        lookup = getattr(self, "_service_lookup", None)
        if lookup is None:
            return {"status": "unknown"}
        try:
            result = self.get_client(lookup).check()
        except Exception:
            self.state = "unknown"
            return {"status": "unknown"}
        self.state = "running"
        return result

    def get_secrets(self) -> dict:
        lookup = getattr(self, "_service_lookup", None)
        if lookup is None:
            raise ValueError("DuckLake service is not bound to an infrastructure")
        return self._connection_secret(lookup)


class _LiveServiceSecrets:
    """Resolve service credentials afresh whenever a client connects."""
    def __init__(self, service, infra):
        self.service = service
        self.infra = infra

    def load_secret(self, name):
        if name != self.service.uuid:
            return None
        return self.service._connection_secret(self.infra)
