from __future__ import annotations
import yaml
import logging

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, cast

from mlox.service import AbstractService
from mlox.services.redis.docker import RedisDockerService
from mlox.services.postgres.docker import PostgresDockerService


logger = logging.getLogger(__name__)


@dataclass
class FeastDockerService(AbstractService):
    """Deploy the Feast registry while reusing remote online/offline stores."""

    dockerfile: str
    registry_port: str | int
    project_name: str

    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {
            "Feast Init": "feast_init",
            "Feast Registry": "feast_registry",
        },
    )

    online_store_uuid: str
    offline_store_uuid: str
    registry_host: str = field(init=False, default="")

    def setup(self, conn) -> None:  # noqa: C901
        redis = self.get_dependent_service(self.online_store_uuid)
        postgres = self.get_dependent_service(self.offline_store_uuid)
        if not redis or not postgres:
            raise ValueError(
                "Feast service requires both online_store_uuid and offline_store_uuid to be set"
            )
        redis_service = cast(RedisDockerService, redis)
        postgres_service = cast(PostgresDockerService, postgres)

        redis_host = redis_service.service_urls["Redis IP"]
        postgres_host = postgres_service.service_urls["Postgres IP"]

        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.fs_copy(conn, self.dockerfile, f"{self.target_path}/Dockerfile")
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        self.registry_host = conn.host

        redis_cert_path = f"{self.target_path}/redis_ca.pem"
        postgres_cert_path = f"{self.target_path}/postgres_ca.pem"
        self.exec.fs_write_file(conn, redis_cert_path, redis.certificate)
        self.exec.fs_write_file(conn, postgres_cert_path, postgres.certificate)

        registry_port = int(self.registry_port)

        config_dict = {
            "project": self.project_name,
            "provider": "local",
            "registry": "data/registry.db",
            # "registry": {
            #     "registry_type": "local",
            #     # "path": f"{conn.host}:{registry_port}",
            #     "path"
            #     "cert": "/certs/feast_registry.pem",
            # },
            "online_store": {
                "type": "redis",
                "redis_type": "redis",
                "connection_string": (
                    f"rediss://:{redis_service.pw}@{redis_host}:{redis_service.port}"
                ),
                # "ssl": True,
                # "ssl_cert": "/certs/redis_ca.pem",
            },
            "offline_store": {
                "type": "postgres",
                "host": postgres_host,
                "port": postgres_service.port,
                "database": postgres_service.db,
                "user": postgres_service.user,
                "password": postgres_service.pw,
                "sslmode": "require",
                # "sslrootcert": "/certs/postgres_ca.pem",
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
            state = self.exec.docker_service_state(
                conn, self.compose_service_names["Feast Registry"]
            )
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
        return {"feast_registry": payload}
