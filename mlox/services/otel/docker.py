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
from urllib.parse import unquote

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
    config: str
    port_grpc: str | int
    port_http: str | int
    port_health: str | int
    grafana_cloud_endpoint: str = ""
    grafana_cloud_key: str = ""
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"OpenTelemetry Collector": "otel-collector"},
    )

    def _has_new_relic_exporter(self) -> bool:
        return len(self.relic_key) > 4 and len(self.relic_endpoint) > 4

    def _has_grafana_cloud_exporter(self) -> bool:
        return len(self.grafana_cloud_key) > 4 and len(self.grafana_cloud_endpoint) > 4

    @staticmethod
    def _normalize_auth_header(value: str) -> str:
        normalized = unquote((value or "").strip()).strip("'\"")
        parts = normalized.split()
        if len(parts) >= 2 and parts[0].lower() in {"basic", "bearer"}:
            return f"{parts[0]} {parts[1]}"
        return normalized

    def _pipeline_exporter_list(self) -> str:
        exporters = ["debug", "file"]
        if self._has_new_relic_exporter():
            exporters.append("otlphttp/new_relic")
        if self._has_grafana_cloud_exporter():
            exporters.append("otlphttp/grafana_cloud")
        return ", ".join(exporters)

    def _new_relic_exporter_block(self) -> str:
        if not self._has_new_relic_exporter():
            return ""
        return (
            '  otlphttp/new_relic: { endpoint: "${env:MY_OTEL_RELIC_ENDPOINT}", '
            'headers: {"api-key": "${env:MY_OTEL_RELIC_KEY}"} }'
        )

    def _grafana_cloud_exporter_block(self) -> str:
        if not self._has_grafana_cloud_exporter():
            return ""
        return (
            '  otlphttp/grafana_cloud: { endpoint: "${env:MY_OTEL_GRAFANA_CLOUD_ENDPOINT}", '
            'headers: {Authorization: "${env:MY_OTEL_GRAFANA_CLOUD_KEY}"} }'
        )

    def get_telemetry_data(self, bundle) -> Any:
        with bundle.server.get_server_connection() as conn:
            data = self.exec.fs_read_file(
                conn, f"{self.target_path}/otel-data/telemetry.json", format="txt/plain"
            )
        return data

    def setup(self, conn) -> None:
        self.grafana_cloud_key = self._normalize_auth_header(self.grafana_cloud_key)

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

        self.exec.fs_copy(
            conn, self.template, f"{self.target_path}/{self.target_docker_script}"
        )
        config_path = f"{self.target_path}/otel-collector-config.yaml"
        self.exec.fs_copy(conn, self.config, config_path)

        exporter_list = self._pipeline_exporter_list()
        for placeholder in (
            "__TRACES_EXPORTER_LIST__",
            "__METRICS_EXPORTER_LIST__",
            "__LOGS_EXPORTER_LIST__",
        ):
            self.exec.fs_find_and_replace(conn, config_path, placeholder, exporter_list)
        self.exec.fs_find_and_replace(
            conn,
            config_path,
            "__NEW_RELIC_EXPORTER_BLOCK__",
            self._new_relic_exporter_block(),
        )
        self.exec.fs_find_and_replace(
            conn,
            config_path,
            "__GRAFANA_CLOUD_EXPORTER_BLOCK__",
            self._grafana_cloud_exporter_block(),
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
        self.exec.fs_append_line(
            conn, env_path, f"OTEL_RELIC_ENDPOINT={self.relic_endpoint}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"OTEL_GRAFANA_CLOUD_KEY={self.grafana_cloud_key}"
        )
        self.exec.fs_append_line(
            conn,
            env_path,
            f"OTEL_GRAFANA_CLOUD_ENDPOINT={self.grafana_cloud_endpoint}",
        )
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
        service_name = self.compose_service_names.get(
            "OpenTelemetry Collector", "otel-collector"
        )
        docker_state = self.exec.docker_service_state(conn, service_name)
        if docker_state not in {"running", "created", "restarting"}:
            alt_name = service_name.replace("-", "_")
            if alt_name != service_name:
                alt_state = self.exec.docker_service_state(conn, alt_name)
                if alt_state in {"running", "created", "restarting"}:
                    docker_state = alt_state
        status = "failed"
        if docker_state == "running":
            status = "running"
        elif docker_state in ("created", "restarting"):
            status = "starting"

        return {"status": status, "docker_state": docker_state}

    def get_secrets(self) -> Dict[str, Dict]:
        secrets: Dict[str, Dict] = {}

        if self.service_url and self.certificate:
            secrets["otel_client_connection"] = {
                "collector_url": self.service_url,
                "trusted_certs": self.certificate,
                "insecure_tls": False,
                "protocol": "otlp_grpc",
            }

        if self._has_new_relic_exporter():
            secrets["new_relic_exporter"] = {
                "license_key": self.relic_key,
                "endpoint": self.relic_endpoint,
            }

        if self._has_grafana_cloud_exporter():
            secrets["grafana_cloud_exporter"] = {
                "api_key": self.grafana_cloud_key,
                "endpoint": self.grafana_cloud_endpoint,
            }

        return secrets
