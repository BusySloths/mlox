import base64
import logging
import secrets
import shlex

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService, tls_setup_no_config
from mlox.remote import (
    docker_down,
    docker_all_service_states,
    exec_command,
    fs_append_line,
    fs_copy,
    fs_create_dir,
    fs_create_empty_file,
    fs_delete_dir,
    fs_read_file,
)


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _generate_cluster_id() -> str:
    """Return a valid Kafka cluster id (base64-url, no padding)."""

    raw = secrets.token_bytes(16)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@dataclass
class KafkaDockerService(AbstractService):
    """Docker based deployment for a single-node Kafka broker."""

    ssl_password: str
    ssl_port: str | int
    service_url: str = field(init=False, default="")
    container_name: str = field(init=False, default="kafka")
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"Kafka Broker": "kafka"},
    )
    cluster_id: str = field(default_factory=_generate_cluster_id, init=False)

    def setup(self, conn) -> None:
        fs_create_dir(conn, self.target_path)
        fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")

        # Generate self-signed TLS assets for the broker
        tls_setup_no_config(conn, conn.host, self.target_path)

        # For PEM setup, cert.pem and key.pem already exist from tls_setup_no_config
        # Create files with names expected by Bitnami entrypoint
        exec_command(
            conn,
            (
                f"cd {self.target_path}; "
                f"cp cert.pem kafka.keystore.pem && "
                f"cp key.pem kafka.keystore.key && "
                f"cp cert.pem kafka.truststore.pem && "
                f"chmod 644 kafka.keystore.key && chmod 644 kafka.keystore.pem kafka.truststore.pem"
            ),
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        fs_create_empty_file(conn, env_path)
        fs_append_line(conn, env_path, f"MY_KAFKA_CLUSTER_ID={self.cluster_id}")
        fs_append_line(conn, env_path, f"MY_KAFKA_SSL_PORT={self.ssl_port}")
        fs_append_line(conn, env_path, f"MY_KAFKA_PUBLIC_HOST={conn.host}")
        # PEM mode: compose file supplies the SSL_* PEM config and mounts certs
        fs_append_line(
            conn,
            env_path,
            f"MY_KAFKA_SSL_KEY_PASSWORD={self.ssl_password}",
        )

        self.certificate = fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        self.service_ports["Kafka SSL"] = int(self.ssl_port)
        self.service_url = f"ssl://{conn.host}:{self.ssl_port}"
        self.service_urls["Kafka Broker"] = self.service_url

    def teardown(self, conn) -> None:
        docker_down(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            remove_volumes=True,
        )
        fs_delete_dir(conn, self.target_path)

    def spin_up(self, conn) -> bool:
        return self.compose_up(conn)

    def spin_down(self, conn) -> bool:
        return self.compose_down(conn)

    def check(self, conn) -> Dict:
        try:
            states = docker_all_service_states(conn)
            if not states:
                self.state = "stopped"
                return {"status": "stopped"}

            container_state = states.get(self.container_name)
            if not container_state:
                self.state = "stopped"
                return {"status": "stopped"}

            health = container_state.get("Health", {})
            status = container_state.get("Status")
            if health.get("Status") == "healthy" or status == "running":
                self.state = "running"
                result = {"status": "running"}
                if health:
                    result["health"] = health.get("Status")
                return result

            self.state = "stopped"
            return {"status": status or "unknown"}
        except Exception as exc:  # pragma: no cover - defensive path
            logger.error("Error checking Kafka service status: %s", exc)
            self.state = "unknown"
            return {"status": "unknown", "error": str(exc)}
