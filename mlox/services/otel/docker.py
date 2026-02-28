"""Docker deployment adapter for OpenTelemetry collector and observability stack.

Purpose:
- Configure OTel collector compose services, certificates, and telemetry endpoint exposure.

Key public classes/functions:
- ``OtelDockerService``

Expected runtime mode:
- Remote executor (invoked from CLI/UI/TUI orchestration)

Related modules (plain-text links):
- mlox.service
- mlox.services.otel.ui
- mlox.services.otel.client
"""

import logging

from dataclasses import dataclass, field
from typing import Dict, Any

from mlox.executors import TaskGroup
from mlox.service import AbstractService

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class OtelDockerService(AbstractService):
    relic_endpoint: str
    relic_key: str
    grafana_endpoint: str
    grafana_auth: str
    influx_endpoint: str
    influx_auth: str
    config: str
    port_grpc: str | int
    port_http: str | int
    port_health: str | int
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"OpenTelemetry Collector": "otel-collector"},
    )

    def get_telemetry_data(self, bundle) -> Any:
        with bundle.server.get_server_connection() as conn:
            data = self.exec.fs_read_file(
                conn, f"{self.target_path}/otel-data/telemetry.json", format="txt/plain"
            )
        return data

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_create_dir(conn, f"{self.target_path}/otel-data")
        telemetry_file = f"{self.target_path}/otel-data/telemetry.json"
        self.exec.fs_touch(conn, telemetry_file)
        self.exec.fs_set_permissions(
            conn,
            f"{self.target_path}/otel-data",
            "777",
            sudo=True,
        )
        self.exec.fs_set_permissions(conn, telemetry_file, "777", sudo=True)

        self.exec.fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        config_template = self.exec.fs_read_file(conn, self.config, format="txt/plain")
        exporters = self._active_exporters()
        config_rendered = config_template.replace(
            "__OPTIONAL_EXPORTERS__",
            f", {', '.join(exporters)}" if exporters else "",
        )
        self.exec.fs_write_file(
            conn,
            f"{self.target_path}/otel-collector-config.yaml",
            config_rendered,
        )

        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )
        # setup env file
        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(conn, env_path, f"OTEL_PORT_GRPC={self.port_grpc}")
        self.exec.fs_append_line(conn, env_path, f"OTEL_PORT_HTTP={self.port_http}")
        self.exec.fs_append_line(conn, env_path, f"OTEL_PORT_HEALTH={self.port_health}")
        self.exec.fs_append_line(conn, env_path, f"OTEL_RELIC_KEY={self.relic_key}")
        self.exec.fs_append_line(conn, env_path, f"OTEL_RELIC_ENDPOINT={self.relic_endpoint}")
        self.exec.fs_append_line(
            conn,
            env_path,
            f"OTEL_GRAFANA_ENDPOINT={self.grafana_endpoint}",
        )
        self.exec.fs_append_line(conn, env_path, f"OTEL_GRAFANA_AUTH={self.grafana_auth}")
        self.exec.fs_append_line(
            conn,
            env_path,
            f"OTEL_INFLUX_ENDPOINT={self.influx_endpoint}",
        )
        self.exec.fs_append_line(conn, env_path, f"OTEL_INFLUX_AUTH={self.influx_auth}")
        self.service_url = f"https://{conn.host}:{self.port_grpc}"
        self.service_ports["OTLP gRPC receiver"] = int(self.port_grpc)
        self.service_ports["OTLP HTTP receiver"] = int(self.port_http)
        self.service_ports["OTEL health check"] = int(self.port_health)
        self.service_urls["OTLP gRPC receiver"] = (
            f"https://{conn.host}:{self.port_grpc}"
        )
        self.service_urls["OTLP HTTP receiver"] = (
            f"https://{conn.host}:{self.port_http}"
        )
        self.service_urls["OTLP health"] = (
            f"https://{conn.host}:{self.port_health}/health/status"
        )
        self.state = "running"

    def teardown(self, conn):
        self.exec.docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        self.exec.fs_delete_dir(conn, self.target_path)
        self.state = "un-initialized"

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        docker_state = self.exec.docker_service_state(conn, "otel-collector")
        status = "failed"
        if docker_state == "running":
            status = "running"
        elif docker_state in ("created", "restarting"):
            status = "starting"

        return {"status": status, "docker_state": docker_state}

    def get_secrets(self) -> Dict[str, Dict]:
        secrets: Dict[str, Dict] = {}

        relic_payload = {
            key: value
            for key, value in {
                "license_key": self.relic_key,
                "endpoint": self.relic_endpoint,
            }.items()
            if value
        }
        if relic_payload:
            secrets["new_relic_exporter"] = relic_payload

        grafana_payload = {
            key: value
            for key, value in {
                "endpoint": self.grafana_endpoint,
                "authorization": self.grafana_auth,
            }.items()
            if value
        }
        if grafana_payload:
            secrets["grafana_cloud_exporter"] = grafana_payload

        influx_payload = {
            key: value
            for key, value in {
                "endpoint": self.influx_endpoint,
                "authorization": self.influx_auth,
            }.items()
            if value
        }
        if influx_payload:
            secrets["influxdb_exporter"] = influx_payload

        return secrets

    def _active_exporters(self) -> list[str]:
        exporters: list[str] = []
        if len(self.relic_key) > 4 and len(self.relic_endpoint) > 4:
            exporters.append("otlphttp/newrelic")
        if len(self.grafana_auth) > 4 and len(self.grafana_endpoint) > 4:
            exporters.append("otlphttp/grafana")
        if len(self.influx_auth) > 4 and len(self.influx_endpoint) > 4:
            exporters.append("otlphttp/influxdb")
        return exporters
