from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import yaml

from mlox.service import AbstractService


logger = logging.getLogger(__name__)


@dataclass
class FeastDockerService(AbstractService):
    """Deploy the Feast registry while reusing remote online/offline stores."""

    dockerfile: str
    registry_port: str | int
    project_name: str
    online_store_service: Optional[AbstractService]
    offline_store_service: Optional[AbstractService]

    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "Feast Init": "feast-init",
            "Feast Registry": "feast-registry",
        },
    )

    registry_host: str = field(init=False, default="")
    online_store_uuid: str = field(init=False, default="")
    offline_store_uuid: str = field(init=False, default="")

    def setup(self, conn) -> None:  # noqa: C901
        redis_service = self._require_service(self.online_store_service, "Redis")
        postgres_service = self._require_service(self.offline_store_service, "Postgres")

        redis_info = self._extract_connection(redis_service, "redis_connection")
        postgres_info = self._extract_connection(postgres_service, "postgres_connection")

        redis_host = redis_info.get("host") or self._resolve_service_host(redis_service, "Redis")
        postgres_host = postgres_info.get("host") or self._resolve_service_host(
            postgres_service, "Postgres"
        )

        redis_port = self._to_int(
            redis_info.get("port") or redis_service.service_ports.get("Redis")
        )
        postgres_port = self._to_int(
            postgres_info.get("port") or postgres_service.service_ports.get("Postgres")
        )

        if not redis_host:
            raise ValueError("Redis service did not expose a host via get_secrets().")
        if not postgres_host:
            raise ValueError("Postgres service did not expose a host via get_secrets().")
        if redis_port <= 0:
            raise ValueError("Redis service did not expose a valid port via get_secrets().")
        if postgres_port <= 0:
            raise ValueError(
                "Postgres service did not expose a valid port via get_secrets()."
            )

        self.online_store_uuid = redis_service.uuid
        self.offline_store_uuid = postgres_service.uuid

        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        self.exec.fs_copy(conn, self.dockerfile, f"{self.target_path}/Dockerfile")
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        self.registry_host = conn.host

        redis_password = redis_info.get("password", "")
        redis_certificate = redis_info.get("certificate", "") or getattr(
            redis_service, "certificate", ""
        )
        postgres_database = postgres_info.get("database", "") or getattr(
            postgres_service, "db", ""
        )
        postgres_user = postgres_info.get("username", "") or getattr(
            postgres_service, "user", ""
        )
        postgres_password = postgres_info.get("password", "") or getattr(
            postgres_service, "pw", ""
        )
        postgres_certificate = postgres_info.get("certificate", "") or getattr(
            postgres_service, "certificate", ""
        )

        redis_cert_path = f"{self.target_path}/redis_ca.pem"
        postgres_cert_path = f"{self.target_path}/postgres_ca.pem"
        self.exec.fs_write_file(conn, redis_cert_path, redis_certificate or "")
        self.exec.fs_write_file(conn, postgres_cert_path, postgres_certificate or "")

        registry_port = int(self.registry_port)

        config_dict = {
            "project": self.project_name,
            "provider": "local",
            "registry": {
                "registry_type": "remote",
                "path": f"{conn.host}:{registry_port}",
            },
            "online_store": {
                "type": "redis",
                "redis_type": "redis",
                "connection_string": (
                    f"rediss://:{redis_password}@" f"{redis_host}:{redis_port}"
                ),
                "ssl": True,
                "ssl_cert": "/certs/redis_ca.pem",
            },
            "offline_store": {
                "type": "postgres",
                "host": postgres_host,
                "port": postgres_port,
                "database": postgres_database,
                "user": postgres_user,
                "password": postgres_password,
                "sslmode": "require",
                "sslrootcert": "/certs/postgres_ca.pem",
            },
            "entity_key_serialization_version": 3,
            "auth": {"type": "no_auth"},
            "telemetry": False,
        }
        config_yaml = yaml.safe_dump(config_dict, sort_keys=False)
        self.exec.fs_write_file(
            conn,
            f"{self.target_path}/feature_store.yaml",
            config_yaml,
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        for line in (
            f"FEAST_PROJECT_NAME={self.project_name}",
            f"FEAST_REGISTRY_PORT={registry_port}",
        ):
            self.exec.fs_append_line(conn, env_path, line)

        self.service_ports = {"registry": registry_port}
        self.service_urls["Feast Registry"] = f"grpc://{conn.host}:{registry_port}"
        self.service_url = f"grpc://{conn.host}:{registry_port}"

    def teardown(self, conn):
        self.exec.docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        try:
            state = self.exec.docker_service_state(conn, self.compose_service_names["Feast Registry"])
            if state and state.strip() == "running":
                self.state = "running"
                return {"status": "running"}
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to determine Feast registry state: %s", exc)
        self.state = "unknown"
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        payload: Dict[str, str] = {
            "registry_host": self.registry_host,
            "registry_port": str(self.registry_port),
            "certificate": self.certificate,
            "project": self.project_name,
            "online_store_uuid": self.online_store_uuid,
            "offline_store_uuid": self.offline_store_uuid,
        }
        secrets: Dict[str, Dict[str, Any]] = {"feast_registry": payload}
        if self.online_store_uuid:
            secrets["feast_online_store"] = {"service_uuid": self.online_store_uuid}
        if self.offline_store_uuid:
            secrets["feast_offline_store"] = {"service_uuid": self.offline_store_uuid}
        return secrets

    @staticmethod
    def _require_service(service: Optional[AbstractService], label: str) -> AbstractService:
        if not service:
            raise ValueError(f"Feast requires a linked {label} service")
        return service

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_connection(
        service: AbstractService, key: str
    ) -> Dict[str, Any]:
        secrets = service.get_secrets() or {}
        payload = secrets.get(key, {})
        if not isinstance(payload, dict):
            logger.warning(
                "Service %s did not provide %s secrets; using empty defaults",
                service.name,
                key,
            )
            return {}
        return payload

    @staticmethod
    def _resolve_service_host(service: AbstractService, label: str) -> str:
        if hasattr(service, "service_urls"):
            for key, value in service.service_urls.items():
                if key.endswith("IP") and isinstance(value, str) and value:
                    return value
        host = getattr(service, "service_url", "")
        if isinstance(host, str) and host:
            try:
                return host.split("//", 1)[-1].split(":", 1)[0]
            except Exception:  # pragma: no cover - defensive fallback
                return host
        raise ValueError(f"{label} service did not expose a host")
