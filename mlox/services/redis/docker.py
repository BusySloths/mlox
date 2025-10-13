import logging

from dataclasses import dataclass, field
from typing import Dict

from mlox.service import AbstractService



# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass
class RedisDockerService(AbstractService):
    pw: str
    port: str | int
    compose_service_names: Dict[str, str] = field(
        init=False,
        default_factory=lambda: {"Redis": "redis"},
    )

    def setup(self, conn) -> None:
        self.exec.fs_create_dir(conn, self.target_path)

        self.exec.fs_copy(conn, self.template, f"{self.target_path}/{self.target_docker_script}")
        self.exec.tls_setup(conn, conn.host, self.target_path)
        self.certificate = self.exec.fs_read_file(
            conn, f"{self.target_path}/cert.pem", format="txt/plain"
        )

        env_path = f"{self.target_path}/{self.target_docker_env}"
        self.exec.fs_append_line(conn, env_path, f"MY_REDIS_PORT={self.port}")
        self.exec.fs_append_line(conn, env_path, f"MY_REDIS_PW={self.pw}")

        self.service_ports["Redis"] = int(self.port)
        self.service_urls["Redis"] = f"https://{conn.host}:{self.port}"
        self.service_urls["Redis IP"] = f"{conn.host}"

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
        # client = redis.Redis(
        #     host=service.params.get("host", "localhost"),
        #     port=service.params.get("port", 6379),
        #     password=service.params.get("password", None),
        #     decode_responses=True,
        # )
        # pong = client.ping()
        # assert pong is True
        try:
            state = self.exec.docker_service_state(conn, "redis")
            if state.strip() == "running":
                self.state = "running"
                return {"status": "running"}
            else:
                self.state = "stopped"
                return {"status": "stopped"}
        except Exception as e:
            logging.error(f"Error checking Redis service status: {e}")
            self.state = "unknown"
        return {"status": "unknown"}

    def get_secrets(self) -> Dict[str, Dict]:
        if not self.pw:
            return {}
        return {"redis_auth": {"password": self.pw}}
