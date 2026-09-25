"""Docker deployment adapter for the lightweight MLflow registry gateway."""

import logging
import os
import secrets
import shlex

from dataclasses import dataclass, field
from typing import Any, Dict

from passlib.hash import apr_md5_crypt  # type: ignore

from mlox.executors import TaskGroup
from mlox.secret_manager import AbstractSecretManager, get_encrypted_access_keyfile
from mlox.service import (
    AbstractSecretManagerBindingService,
    AbstractTelemetryBindingService,
    ServiceCapability,
)
from mlox.services.mlflow_gateway.base import (
    MLFlowGatewayService,
    _resolved_setting,
    _resolved_text,
)

logger = logging.getLogger(__name__)


@dataclass
class MLFlowGatewayDockerService(
    AbstractSecretManagerBindingService,
    AbstractTelemetryBindingService,
    MLFlowGatewayService,
):
    capabilities = {
        ServiceCapability.MODEL_SERVER,
        ServiceCapability.HEALTH,
        ServiceCapability.SECRET_MANAGER_BINDING,
        ServiceCapability.TELEMETRY_BINDING,
    }

    hashed_pw: str = field(default="", init=False)

    _SECRET_MANAGER_ENV_KEYS = frozenset(
        {
            "MLOX_SECRET_MANAGER_KEYFILE",
            "MLOX_SECRET_MANAGER_KEYFILE_PW",
        }
    )
    _TELEMETRY_ENV_KEYS = frozenset(
        {
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_PROTOCOL",
            "OTEL_EXPORTER_OTLP_CERTIFICATE",
            "OTEL_EXPORTER_OTLP_INSECURE",
            "OTEL_TRACES_SAMPLER",
            "OTEL_RESOURCE_ATTRIBUTES",
        }
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.target_path.endswith(f"-{self.port}"):
            self.target_path = f"{self.target_path}-{self.port}"
        self.compose_service_names = {
            "Traefik": f"traefik_reverse_proxy_mlflow_gateway_{self.port}",
            "MLflow Gateway": f"mlflow_gateway_{self.port}",
        }

    def _generate_htpasswd_entry(self) -> None:
        self.hashed_pw = apr_md5_crypt.hash(self.pw).replace("$", "$$")

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)
        template = self.resolve_asset(self.template)
        self.exec.fs_copy(
            conn, str(template), f"{self.target_path}/{self.target_docker_script}"
        )
        dockerfile = self.resolve_asset(self.dockerfile)
        self.exec.fs_copy(
            conn,
            str(dockerfile),
            f"{self.target_path}/{os.path.basename(self.dockerfile)}",
        )
        serve_script = self.resolve_asset(self.serve_script)
        self.exec.fs_copy(conn, str(serve_script), f"{self.target_path}/serve.py")
        start_script = self.resolve_asset(self.start_script)
        self.exec.fs_copy(
            conn,
            str(start_script),
            f"{self.target_path}/{os.path.basename(self.start_script)}",
        )
        self.exec.fs_write_file(
            conn,
            f"{self.target_path}/gateway-requirements.txt",
            _resolved_text(self.requirements_txt or ""),
        )
        self.exec.fs_create_empty_file(conn, f"{self.target_path}/otel-ca.pem")

        self._generate_htpasswd_entry()

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_create_empty_file(conn, env_path)
        self.exec.fs_append_line(
            conn, env_path, f"TRAEFIK_USER_AND_PW={self.user}:{self.hashed_pw}"
        )
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_GATEWAY_URL={conn.host}")
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_GATEWAY_PORT={self.port}")
        self.exec.fs_append_line(
            conn, env_path, f"MLFLOW_REMOTE_URI={self.tracking_uri}"
        )
        self.exec.fs_append_line(
            conn, env_path, f"MLFLOW_REMOTE_USER={self.tracking_user}"
        )
        self.exec.fs_append_line(conn, env_path, f"MLFLOW_REMOTE_PW={self.tracking_pw}")
        self.exec.fs_append_line(conn, env_path, "MLFLOW_REMOTE_INSECURE=true")
        self.exec.fs_append_line(
            conn,
            env_path,
            "MLOX_GATEWAY_CACHE_MAX_MODELS="
            f"{_resolved_setting(self.cache_max_models, '10')}",
        )
        self.exec.fs_append_line(
            conn,
            env_path,
            f"MLOX_GATEWAY_CACHE_TTL_DAYS={_resolved_setting(self.cache_ttl_days, '10')}",
        )

        if self.secret_manager_uuid:
            manager = self.get_bound_secret_manager()
            if manager is not None:
                self._apply_secret_manager_binding(
                    conn,
                    manager_uuid=self.secret_manager_uuid,
                    manager=manager,
                )
        if self.telemetry_uuid:
            connection = self.get_bound_telemetry_secrets()
            if connection is not None:
                self._apply_telemetry_binding(
                    conn,
                    telemetry_uuid=self.telemetry_uuid,
                    connection=connection,
                )

        self.service_ports["MLflow Gateway REST API"] = int(self.port)
        self.service_urls["MLflow Gateway REST API"] = (
            f"https://{conn.host}:{self.port}"
        )
        self.service_url = f"https://{conn.host}:{self.port}"

    def _update_runtime_environment(
        self,
        conn,
        *,
        managed_keys: frozenset[str],
        values: Dict[str, str] | None,
    ) -> None:
        """Replace one MLOX-owned block in the Compose environment file."""

        env_path = f"{self.target_path}/{self.target_docker_env}"
        try:
            current = self.exec.fs_read_file(conn, env_path, format="string") or ""
        except Exception:
            current = ""
        lines = []
        for raw_line in str(current).splitlines():
            key = raw_line.split("=", 1)[0].strip()
            if key not in managed_keys:
                lines.append(raw_line)
        for key, value in (values or {}).items():
            if key in managed_keys:
                lines.append(f"{key}={value}")
        content = "\n".join(lines)
        if content:
            content += "\n"
        self.exec.fs_write_file(conn, env_path, content)
        if self.state in {"running", "unknown"}:
            self.compose_restart(conn)

    def _apply_secret_manager_binding(
        self,
        conn,
        *,
        manager_uuid: str,
        manager: AbstractSecretManager,
    ) -> None:
        keyfile_password = secrets.token_urlsafe(32)
        encrypted_keyfile = get_encrypted_access_keyfile(
            manager, keyfile_password
        )
        self._update_runtime_environment(
            conn,
            managed_keys=self._SECRET_MANAGER_ENV_KEYS,
            values={
                "MLOX_SECRET_MANAGER_KEYFILE": encrypted_keyfile,
                "MLOX_SECRET_MANAGER_KEYFILE_PW": keyfile_password,
            },
        )

    def _remove_secret_manager_binding(self, conn) -> None:
        self._update_runtime_environment(
            conn,
            managed_keys=self._SECRET_MANAGER_ENV_KEYS,
            values=None,
        )

    def _apply_telemetry_binding(
        self,
        conn,
        *,
        telemetry_uuid: str,
        connection: Dict[str, Any],
    ) -> None:
        endpoint = str(
            connection.get("collector_url") or connection.get("endpoint") or ""
        ).strip()
        if not endpoint:
            raise ValueError("Telemetry connection does not define a collector URL.")
        protocol = str(connection.get("protocol") or "grpc").strip().lower()
        if protocol == "otlp_grpc":
            protocol = "grpc"
        certificate = str(connection.get("trusted_certs") or "")
        certificate_path = f"{self.target_path}/otel-ca.pem"
        if certificate:
            self.exec.fs_write_file(conn, certificate_path, certificate)
        insecure = str(bool(connection.get("insecure_tls", False))).lower()
        values = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
            "OTEL_EXPORTER_OTLP_PROTOCOL": protocol,
            "OTEL_EXPORTER_OTLP_INSECURE": insecure,
            "OTEL_TRACES_SAMPLER": "always_on",
            "OTEL_RESOURCE_ATTRIBUTES": (
                f"service.name={self.name},mlox.service.uuid={self.uuid}"
            ),
        }
        if certificate:
            values["OTEL_EXPORTER_OTLP_CERTIFICATE"] = "/run/mlox/otel-ca.pem"
        self._update_runtime_environment(
            conn,
            managed_keys=self._TELEMETRY_ENV_KEYS,
            values=values,
        )

    def _remove_telemetry_binding(self, conn) -> None:
        self._update_runtime_environment(
            conn,
            managed_keys=self._TELEMETRY_ENV_KEYS,
            values=None,
        )

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
                conn, self.compose_service_names.get("MLflow Gateway", "")
            )
            if state and state.strip() == "running":
                host = shlex.quote(conn.host)
                user = shlex.quote(self.user)
                pw = shlex.quote(self.pw)
                url = shlex.quote(f"{self.service_url}/health")
                cmd = (
                    "curl -s -o /dev/null -w '%{http_code}' -k "
                    f"-u {user}:{pw} -H 'Host: {host}' {url}"
                )
                code = self.exec.execute(
                    conn,
                    command=cmd,
                    group=TaskGroup.NETWORKING,
                    description="Check MLflow Gateway health",
                )
                if code and code.strip() == "200":
                    self.state = "running"
                    return {"status": "running"}
                self.state = "unknown"
                return {"status": "unknown", "http_code": (code or "").strip()}
            self.state = "stopped"
            return {"status": "stopped"}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.error("Error checking MLflow Gateway status: %s", exc)
            self.state = "unknown"
        return {"status": "unknown"}
