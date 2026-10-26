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
import base64
from shlex import quote

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping
from urllib.parse import unquote

from mlox.service import (
    AbstractHealthService,
    AbstractMonitorService,
    AbstractObservabilityService,
    AbstractService,
    ServiceCapability,
    service_health_payload,
)
from mlox.services.otel.constants import MLOX_OTEL_CERTIFICATE_B64_ENV
from mlox.execution.base import TaskGroup

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class OtelDockerService(
    AbstractService,
    AbstractHealthService,
    AbstractMonitorService,
    AbstractObservabilityService,
):
    capabilities = {
        ServiceCapability.MONITOR,
        ServiceCapability.OBSERVABILITY,
        ServiceCapability.HEALTH,
    }
    relic_endpoint: str
    relic_key: str
    config: str
    port_grpc: str | int
    port_http: str | int
    port_health: str | int
    grafana_cloud_endpoint: str = ""
    grafana_cloud_key: str = ""
    diagnostic_exporter: bool | str = False
    file_destination: bool | str = True
    influx_service_uuid: str | None = None
    grafana_cloud_destination: bool | str = True
    new_relic_destination: bool | str = True
    service_url: str = field(init=False, default="")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"OpenTelemetry Collector": "otel-collector"},
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._normalize_destination_flags()
        # Historical deployments supplied provider credentials directly and did
        # not persist explicit destination toggles.  Keep those destinations
        # enabled when complete, but do not present incomplete defaults as on.
        self._disable_unconfigured_hosted_destinations()
        # Runtime-only material resolved from the selected InfluxDB service.
        # It is intentionally not a dataclass field and is never persisted.
        self._influx_binding: Dict[str, str] | None = None

    def _normalize_destination_flags(self) -> None:
        for name in (
            "diagnostic_exporter",
            "file_destination",
            "grafana_cloud_destination",
            "new_relic_destination",
        ):
            enabled = str(getattr(self, name)).strip().lower() in {
                "1", "true", "yes", "on"
            }
            setattr(self, name, enabled)

    def _has_new_relic_exporter(self) -> bool:
        return (
            self.new_relic_destination
            and len(self.relic_key) > 4
            and len(self.relic_endpoint) > 4
        )

    def _has_grafana_cloud_exporter(self) -> bool:
        return (
            self.grafana_cloud_destination
            and len(self.grafana_cloud_key) > 4
            and len(self.grafana_cloud_endpoint) > 4
        )

    def _disable_unconfigured_hosted_destinations(self) -> None:
        if not self._has_grafana_cloud_exporter():
            self.grafana_cloud_destination = False
        if not self._has_new_relic_exporter():
            self.new_relic_destination = False

    def _validate_hosted_destinations(self) -> None:
        """Reject enabled hosted destinations that lack their credentials."""

        destinations = (
            (
                "Grafana Cloud",
                self.grafana_cloud_destination,
                self.grafana_cloud_endpoint,
                self.grafana_cloud_key,
            ),
            (
                "New Relic",
                self.new_relic_destination,
                self.relic_endpoint,
                self.relic_key,
            ),
        )
        for name, enabled, endpoint, api_key in destinations:
            if enabled and (len(endpoint.strip()) < 5 or len(api_key.strip()) < 5):
                raise ValueError(f"{name} requires an OTLP endpoint and API key.")

    def _resolve_influx_binding(self) -> Dict[str, str] | None:
        """Resolve the selected InfluxDB service without persisting credentials."""

        service_uuid = str(self.influx_service_uuid or "").strip()
        if not service_uuid:
            self._influx_binding = None
            return None
        provider = self.get_dependent_service(
            service_uuid,
            required_capabilities={ServiceCapability.DATABASE},
        )
        if provider is None:
            raise ValueError(
                f"InfluxDB service {service_uuid!r} was not found."
            )
        get_binding = getattr(provider, "get_influx_env_binding", None)
        if not callable(get_binding):
            raise ValueError(
                f"Service {service_uuid!r} does not provide an Influx binding."
            )
        binding = get_binding()
        required = {
            "MLOX_INFLUX_V2_WRITE_ENDPOINT",
            "MLOX_INFLUX_TOKEN",
            "MLOX_INFLUX_ORG",
            "MLOX_INFLUX_DATABASE",
        }
        if not isinstance(binding, Mapping) or not required.issubset(binding):
            raise ValueError(
                "Selected InfluxDB service returned an incomplete binding."
            )
        self._influx_binding = {
            str(key): str(value) for key, value in binding.items()
        }
        return self._influx_binding

    def _has_influx_exporter(self) -> bool:
        binding = self._influx_binding
        return bool(
            binding
            and len(binding.get("MLOX_INFLUX_V2_WRITE_ENDPOINT", "")) > 4
            and len(binding.get("MLOX_INFLUX_TOKEN", "")) > 4
            and bool(binding.get("MLOX_INFLUX_DATABASE", "").strip())
        )

    @staticmethod
    def _normalize_auth_header(value: str) -> str:
        normalized = unquote((value or "").strip()).strip("'\"")
        parts = normalized.split()
        if len(parts) >= 2 and parts[0].lower() in {"basic", "bearer"}:
            return f"{parts[0]} {parts[1]}"
        return normalized

    def _pipeline_exporter_list(self) -> str:
        exporters = ["file"] if self.file_destination else []
        if self.diagnostic_exporter:
            exporters.insert(0, "debug")
        if self._has_new_relic_exporter():
            exporters.append("otlphttp/new_relic")
        if self._has_grafana_cloud_exporter():
            exporters.append("otlphttp/grafana_cloud")
        if self._has_influx_exporter():
            exporters.append("influxdb/influx")
        if not exporters:
            raise ValueError("At least one OpenTelemetry destination must be enabled.")
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

    def _influx_exporter_block(self) -> str:
        if not self._has_influx_exporter():
            return ""
        # InfluxDB 3 Core implements the v2 line-protocol compatibility API.
        # ``org`` is required by the Collector exporter but ignored by Core;
        # ``bucket`` maps to the Core database.  This exporter supports all
        # three signals, unlike the generic OTLP HTTP exporter.
        return "\n".join(
            (
                "  influxdb/influx:",
                '    endpoint: "${env:MY_OTEL_INFLUX_ENDPOINT}"',
                '    org: "${env:MY_OTEL_INFLUX_ORG}"',
                '    bucket: "${env:MY_OTEL_INFLUX_BUCKET}"',
                '    token: "${env:MY_OTEL_INFLUX_TOKEN}"',
                "    tls:",
                "      ca_file: /etc/influx-ca.pem",
                "    precision: ns",
                "    payload_max_lines: 1000",
                "    payload_max_bytes: 1000000",
            )
        )

    def get_telemetry_data(self, bundle) -> Any:
        with bundle.server.get_server_connection() as conn:
            data = self.exec.fs_read_file(
                conn, f"{self.target_path}/otel-data/telemetry.json", format="txt/plain"
            )
        return data

    def get_monitor_snapshot(self, bundle) -> Dict[str, Any]:
        telemetry_raw = self.get_telemetry_data(bundle)
        from mlox.tui.services.otel import _build_resource_snapshot

        snapshot = _build_resource_snapshot(telemetry_raw)
        return {
            "cpu_used_ratio": snapshot.cpu.now_used_ratio,
            "ram_free_ratio": snapshot.memory.free_ratio,
            "disk_free_ratio": snapshot.disk.free_ratio,
            "network_in_rate": snapshot.network.receive_rate,
            "network_out_rate": snapshot.network.transmit_rate,
            "network_unit": snapshot.network.unit,
            "latest_timestamp": snapshot.latest_timestamp,
            "messages": snapshot.messages,
            "metric_points": snapshot.summary.get("metric_points", 0),
        }

    def setup(self, conn) -> None:
        self.grafana_cloud_key = self._normalize_auth_header(self.grafana_cloud_key)
        self._resolve_influx_binding()

        self.exec.fs_create_dir(conn, self.target_path)
        self.exec.fs_create_dir(conn, f"{self.target_path}/otel-data")
        telemetry_file = f"{self.target_path}/otel-data/telemetry.json"
        self.exec.fs_touch(conn, telemetry_file)
        influx_certificate_path = f"{self.target_path}/influx-ca.pem"
        influx_certificate_b64 = str(
            (self._influx_binding or {}).get("MLOX_INFLUX_CERTIFICATE_B64", "")
        )
        if influx_certificate_b64:
            try:
                certificate = base64.b64decode(influx_certificate_b64, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    "Selected InfluxDB service returned an invalid certificate."
                ) from exc
            self.exec.fs_write_file(
                conn, influx_certificate_path, certificate.decode("utf-8")
            )
        else:
            self.exec.fs_create_empty_file(conn, influx_certificate_path)
        self.exec.fs_set_permissions(
            conn,
            f"{self.target_path}/otel-data",
            "777",
            sudo=True,
        )
        self.exec.fs_set_permissions(conn, telemetry_file, "777", sudo=True)
        self.exec.fs_set_permissions(conn, influx_certificate_path, "600", sudo=True)

        template = self.resolve_asset(self.template)
        self.exec.fs_copy(
            conn, str(template), f"{self.target_path}/{self.target_docker_script}"
        )
        config_path = f"{self.target_path}/otel-collector-config.yaml"
        config = self.resolve_asset(self.config)
        self.exec.fs_copy(conn, str(config), config_path)

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
        self.exec.fs_find_and_replace(
            conn,
            config_path,
            "__INFLUX_EXPORTER_BLOCK__",
            self._influx_exporter_block(),
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
        influx_binding = self._influx_binding or {}
        self.exec.fs_append_line(
            conn,
            env_path,
            "OTEL_INFLUX_ENDPOINT="
            f"{influx_binding.get('MLOX_INFLUX_V2_WRITE_ENDPOINT', '')}",
        )
        self.exec.fs_append_line(
            conn,
            env_path,
            f"OTEL_INFLUX_TOKEN={influx_binding.get('MLOX_INFLUX_TOKEN', '')}",
        )
        self.exec.fs_append_line(
            conn,
            env_path,
            f"OTEL_INFLUX_ORG={influx_binding.get('MLOX_INFLUX_ORG', '')}",
        )
        self.exec.fs_append_line(
            conn,
            env_path,
            f"OTEL_INFLUX_BUCKET={influx_binding.get('MLOX_INFLUX_DATABASE', '')}",
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

    def get_health(self, conn) -> Dict[str, Any]:
        payload = self.check(conn)
        health_url = self.service_urls.get("OTLP health")
        if health_url:
            payload["health_url"] = health_url
        return service_health_payload(self, payload)

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
        if self.influx_service_uuid:
            secrets["influx_destination"] = {
                "service_uuid": self.influx_service_uuid,
                "configured": self._has_influx_exporter(),
            }

        return secrets

    def collector_destinations(self) -> Dict[str, bool]:
        """Declarative all-signal destination state, safe for TUI display."""
        return {
            "file": bool(self.file_destination),
            "influx": bool(self.influx_service_uuid),
            "grafana_cloud": self._has_grafana_cloud_exporter(),
            "new_relic": self._has_new_relic_exporter(),
        }

    def _destination_failure_message(self, error: Exception) -> str:
        """Return an actionable failure reason without exposing credentials."""

        detail = str(error).strip() or "collector destination update failed"
        sensitive_values = [self.relic_key, self.grafana_cloud_key]
        sensitive_values.extend((self._influx_binding or {}).values())
        for value in sensitive_values:
            if value and len(value) >= 5:
                detail = detail.replace(value, "[redacted]")
        return detail[:500]

    def update_destinations(self, conn, **destinations: Any) -> Dict[str, Any]:
        """Render, validate, restart, health-check, and roll back destinations.

        The configuration is rendered from the same declarative fields as setup.
        A failed restart or health check is immediately followed by a render and
        restart of the last known-good fields; secrets remain in the protected
        env file and are never returned in this result.
        """
        allowed = {
            "file_destination", "influx_service_uuid",
            "grafana_cloud_destination", "grafana_cloud_endpoint",
            "grafana_cloud_key", "new_relic_destination", "relic_endpoint",
            "relic_key", "diagnostic_exporter",
        }
        unknown = set(destinations) - allowed
        if unknown:
            raise ValueError("Unsupported collector destination setting.")
        previous = {name: getattr(self, name) for name in allowed}
        backed_up = False
        try:
            for name, value in destinations.items():
                setattr(self, name, value)
            self._normalize_destination_flags()
            self._validate_hosted_destinations()
            self._resolve_influx_binding()
            # This catches an empty destination set before replacing the config.
            self._pipeline_exporter_list()
            self._backup_collector_files(conn)
            backed_up = True
            self.setup(conn)
            self._validate_rendered_config(conn)
            self.exec.docker_restart(
                conn,
                f"{self.target_path}/{self.target_docker_script}",
                f"{self.target_path}/{self.target_docker_env}",
            )
            health = self.check(conn)
            if health.get("status") != "running":
                raise RuntimeError("collector did not become healthy")
            self._discard_collector_backup(conn)
            return {"updated": True, "destinations": self.collector_destinations()}
        except Exception as error:
            failure_message = self._destination_failure_message(error)
            logging.error("OpenTelemetry collector destination update failed: %s", failure_message)
            for name, value in previous.items():
                setattr(self, name, value)
            self._normalize_destination_flags()
            # Render and recreate the previous healthy configuration.  A second
            # failure is deliberately surfaced instead of hiding an outage.
            try:
                if backed_up:
                    self._restore_collector_backup(conn)
                else:
                    self.setup(conn)
                self.exec.docker_restart(
                    conn,
                    f"{self.target_path}/{self.target_docker_script}",
                    f"{self.target_path}/{self.target_docker_env}",
                )
                restored = self.check(conn).get("status") == "running"
            except Exception:
                restored = False
            return {
                "updated": False,
                "rolled_back": restored,
                "error": failure_message,
            }

    def _backup_collector_files(self, conn) -> None:
        execute = getattr(self.exec, "execute", None)
        if not callable(execute):
            raise RuntimeError("Executor cannot stage collector configuration.")
        config = f"{self.target_path}/otel-collector-config.yaml"
        env = f"{self.target_path}/{self.target_docker_env}"
        command = f"cp {quote(config)} {quote(config + '.previous')} && cp {quote(env)} {quote(env + '.previous')}"
        if execute(conn, command, group=TaskGroup.FILESYSTEM, description="Back up OTel collector config") is None:
            raise RuntimeError("Could not back up collector configuration.")

    def _restore_collector_backup(self, conn) -> None:
        execute = getattr(self.exec, "execute", None)
        if not callable(execute):
            raise RuntimeError("Executor cannot restore collector configuration.")
        config = f"{self.target_path}/otel-collector-config.yaml"
        env = f"{self.target_path}/{self.target_docker_env}"
        command = f"mv {quote(config + '.previous')} {quote(config)} && mv {quote(env + '.previous')} {quote(env)}"
        if execute(conn, command, group=TaskGroup.FILESYSTEM, description="Restore OTel collector config") is None:
            raise RuntimeError("Could not restore collector configuration.")

    def _discard_collector_backup(self, conn) -> None:
        execute = getattr(self.exec, "execute", None)
        if callable(execute):
            config = f"{self.target_path}/otel-collector-config.yaml"
            env = f"{self.target_path}/{self.target_docker_env}"
            execute(conn, f"rm -f {quote(config + '.previous')} {quote(env + '.previous')}", group=TaskGroup.FILESYSTEM, description="Remove OTel config backup")

    def _validate_rendered_config(self, conn) -> None:
        """Validate through Compose so config interpolation sees its runtime env."""
        execute = getattr(self.exec, "execute", None)
        if not callable(execute):
            raise RuntimeError("Executor cannot validate collector configuration.")
        compose_path = f"{self.target_path}/{self.target_docker_script}"
        env_path = f"{self.target_path}/{self.target_docker_env}"
        command = (
            f"docker compose --env-file {quote(env_path)} -f {quote(compose_path)} "
            "run --rm --no-deps otel-collector "
            "validate --config=/etc/otel-collector-config.yaml"
        )
        result = execute(conn, command, group=TaskGroup.CONTAINER_RUNTIME, sudo=True, description="Validate OTel collector config")
        if result is None:
            raise RuntimeError("Collector configuration validation failed.")

    def get_telemetry_env_binding(self) -> Dict[str, str]:
        """Export a complete environment-only OTLP client configuration."""

        connection = self.get_secrets().get("otel_client_connection")
        if not isinstance(connection, dict):
            raise ValueError("OpenTelemetry client connection is not configured.")
        endpoint = str(connection.get("collector_url") or "").strip()
        if not endpoint:
            raise ValueError("OpenTelemetry collector URL is not configured.")
        protocol = str(connection.get("protocol") or "grpc").strip().lower()
        if protocol == "otlp_grpc":
            protocol = "grpc"
        environment = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
            "OTEL_EXPORTER_OTLP_PROTOCOL": protocol,
            "OTEL_EXPORTER_OTLP_INSECURE": str(
                bool(connection.get("insecure_tls", False))
            ).lower(),
            "OTEL_TRACES_SAMPLER": "always_on",
        }
        certificate = connection.get("trusted_certs")
        if certificate:
            if isinstance(certificate, str):
                certificate = certificate.encode("utf-8")
            environment[MLOX_OTEL_CERTIFICATE_B64_ENV] = (
                base64.b64encode(certificate).decode("ascii")
            )
        return environment
