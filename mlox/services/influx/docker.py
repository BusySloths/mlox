"""Docker deployment adapter for InfluxDB service instances.

Purpose:
- Configure InfluxDB container runtime, credentials, and TLS-enabled service exposure.

Key public classes/functions:
- ``InfluxDockerService``

Expected runtime mode:
- Remote executor (invoked from CLI/UI/TUI orchestration)

Related modules (plain-text links):
- mlox.service
- mlox.services.influx.ui
"""

import json
import logging
import shlex

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import (
    AbstractHealthService,
    AbstractService,
    ServiceCapability,
    service_health_payload,
)
from mlox.execution.base import TaskGroup


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class InfluxDockerService(AbstractService, AbstractHealthService):
    capabilities = {ServiceCapability.DATABASE, ServiceCapability.HEALTH}
    user: str
    pw: str
    port: str | int
    token: str
    database: str = "telemetry"
    retention_period: str = "7d"
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"InfluxDB": "influxdb3"},
    )

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)

        template = self.resolve_asset(self.template)
        self.exec.fs_copy(
            conn, str(template), f"{self.target_path}/{self.target_docker_script}"
        )
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_append_line(conn, env_path, f"INFLUXDB_PORT={self.port}")

        # Core bootstraps authorization only from an offline admin-token JSON
        # document. Docker Compose exposes it as a secret, never an environment
        # variable or command-line value.
        token_path = f"{self.target_path}/.influxdb3-admin-token.json"
        self.exec.fs_write_file(
            conn,
            token_path,
            json.dumps(
                {
                    "token": self.token,
                    "name": "mlox-admin",
                    "description": "MLOX-managed InfluxDB 3 Core admin token",
                }
            ),
        )
        # InfluxDB 3 Core runs as UID/GID 1500. Compose mounts local secrets as
        # bind files, so preserve private host access while allowing that group
        # to read the token at /run/secrets/influxdb3-admin-token.
        result = self.exec.execute(
            conn,
            f"chgrp 1500 -- {shlex.quote(token_path)}",
            group=TaskGroup.SECURITY_ASSETS,
            sudo=True,
            description="Grant InfluxDB runtime group access to admin token",
        )
        if result is None:
            raise RuntimeError("Could not set InfluxDB admin token group ownership.")
        self.exec.fs_set_permissions(conn, token_path, "640", sudo=True)

        self.service_ports["InfluxDB"] = int(self.port)
        self.service_urls["InfluxDB"] = f"https://{conn.host}:{self.port}"

    def teardown(self, conn):
        self.exec.docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)

    def spin_up(self, conn) -> bool:
        started = self.compose_up(conn)
        if started:
            self._ensure_database(conn)
        return started

    def _ensure_database(self, conn) -> None:
        """Create the telemetry database with the configured retention policy."""
        from mlox.services.influx.client import InfluxClient

        client = InfluxClient(
            url=f"https://{conn.host}:{self.port}",
            token=self.token,
            database=self.database,
            certificate=str(self.certificate or "").encode("utf-8"),
        )
        try:
            client.create_database(retention_period=self.retention_period)
        except Exception as exc:
            raise RuntimeError(
                f"Could not create InfluxDB database '{self.database}' with "
                f"{self.retention_period} retention. InfluxDB 3 Core does not "
                "change retention on an existing database; create a new database "
                "with this retention and migrate or discard the old database."
            ) from exc

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        try:
            state = self.exec.docker_service_state(conn, "influxdb3")
            return {"status": state, "docker_state": state}
        except Exception as e:
            logging.error(f"Error checking InfluxDB service status: {e}")
            self.state = "unknown"
        return {"status": "unknown"}

    def get_health(self, conn) -> Dict:
        """Return the standard health payload used by the TUI health action."""

        payload = self.check(conn)
        payload["health_url"] = f"{self.service_urls.get('InfluxDB', '')}/health"
        return service_health_payload(self, payload)

    def get_secrets(self) -> Dict[str, Dict]:
        credentials = {
            "token": self.token,
            "certificate": self.certificate,
            "port": str(self.port),
            "url": self.service_urls.get("InfluxDB", None),
            "ip": self.service_urls.get("InfluxDB", "").split("//")[-1].split(":")[0],
            "database": self.database,
        }
        return {"influx_connection": credentials}

    def get_influx_env_binding(self) -> Dict[str, str]:
        """Return runtime-safe Influx configuration (no application secret logic)."""

        import base64

        connection = self.get_secrets()["influx_connection"]
        certificate = str(connection.get("certificate") or "")
        binding = {
            "MLOX_INFLUX_URL": str(connection["url"]),
            "MLOX_INFLUX_TOKEN": str(connection["token"]),
            "MLOX_INFLUX_DATABASE": str(connection["database"]),
            # Collector's Influx exporter speaks the v2 compatibility API.
            "MLOX_INFLUX_V2_WRITE_ENDPOINT": str(connection["url"]).rstrip("/")
            + "/api/v2/write",
            # Core ignores org for v2 compatibility, but the exporter validates it.
            "MLOX_INFLUX_ORG": "mlox",
        }
        if certificate:
            binding["MLOX_INFLUX_CERTIFICATE_B64"] = base64.b64encode(
                certificate.encode("utf-8")
            ).decode("ascii")
        return binding

    def get_telemetry_query_service(self):
        """Return the bounded Operations query backend for this service."""
        from mlox.services.influx.client import InfluxClient
        from mlox.services.influx.telemetry import InfluxTelemetryQueryService

        connection = self.get_secrets()["influx_connection"]
        return InfluxTelemetryQueryService(
            InfluxClient(
                url=str(connection["url"]), token=str(connection["token"]),
                database=str(connection["database"]),
                certificate=str(connection["certificate"]).encode("utf-8"),
            )
        )
