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
    secret_manager_uuid: str
    postgres_secret_name: str
    s3_secret_name: str
    data_path: str
    metadata_schema: str = "ducklake"
    catalog_name: str = "lake"

    def get_client(self, infra: Infrastructure) -> DuckLakeClient:
        from mlox.services.ducklake.client import DuckLakeClient

        dependencies = {}
        for role, uuid, capability in (
            ("PostgreSQL", self.postgres_service_uuid, ServiceCapability.DATABASE),
            ("object storage", self.storage_service_uuid, ServiceCapability.S3_OBJECT_STORAGE),
        ):
            service = infra.get_service_by_uuid(uuid)
            if service is None or capability not in getattr(service, "capabilities", set()):
                raise ValueError(f"Configured {role} service is missing or incompatible")
            dependencies[role] = service
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
        return DuckLakeClient(manager, self.postgres_secret_name, self.s3_secret_name,
                              self.data_path, self.metadata_schema, self.catalog_name,
                              postgres_defaults=postgres_defaults, s3_defaults=s3_defaults)

    def setup(self, conn) -> None:
        # Registration does not create a catalog or access external resources.
        self.state = "running"

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
        return {}
