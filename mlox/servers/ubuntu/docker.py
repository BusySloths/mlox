import logging

import json  # For parsing docker command JSON output
from dataclasses import dataclass
from typing import Dict, Any

from mlox.servers.ubuntu.native import UbuntuNativeServer
from mlox.remote import exec_command

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class UbuntuDockerServer(UbuntuNativeServer):
    def __post_init__(self):
        super().__post_init__()
        self.backend = ["docker"]

    def setup_backend(self) -> None:
        self.state = "starting"
        with self.get_server_connection() as conn:  # MyPy will understand this call
            exec_command(conn, "apt-get -y install ca-certificates curl", sudo=True)
            exec_command(conn, "install -m 0755 -d /etc/apt/keyrings", sudo=True)
            exec_command(
                conn,
                "curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc",
                sudo=True,
            )
            exec_command(conn, "chmod a+r /etc/apt/keyrings/docker.asc", sudo=True)

            # Use double quotes inside the single-quoted sh -c command string
            repo_line = 'deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable'
            full_cmd = (
                f"sh -c 'echo \"{repo_line}\" > /etc/apt/sources.list.d/docker.list'"
            )
            exec_command(
                conn, full_cmd, sudo=True, pty=False
            )  # pty=False should be fine
            exec_command(conn, "apt-get update", sudo=True)
            exec_command(
                conn,
                "apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
                sudo=True,
            )
            print("Done installing docker")
            exec_command(conn, "docker --version", sudo=True)
            self.state = "running"

    def teardown_backend(self) -> None:
        """Uninstalls Docker Engine and related packages."""
        self.state = "shutdown"
        with self.get_server_connection() as conn:
            logger.info("Stopping and disabling Docker service...")
            exec_command(conn, "systemctl stop docker", sudo=True, pty=True)
            exec_command(conn, "systemctl disable docker", sudo=True, pty=True)
            logger.info("Purging Docker packages...")
            exec_command(
                conn,
                "apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras",
                sudo=True,
            )
            logger.info("Removing Docker directories...")
            exec_command(conn, "rm -rf /var/lib/docker", sudo=True)
            exec_command(
                conn, "rm -rf /var/lib/containerd", sudo=True
            )  # Also remove containerd data
            # /etc/docker should be removed by purge, but an extra check doesn't hurt if needed.
            # exec_command(conn, "rm -rf /etc/docker", sudo=True)
            logger.info("Docker uninstalled.")
            self.state = "no-backend"

    def get_backend_status(self) -> Dict[str, Any]:
        status_info: Dict[str, Any] = {}
        with self.get_server_connection() as conn:
            # Check Docker status
            # systemctl is-active returns 0 for active, non-zero otherwise
            # pty=False is generally better for non-interactive status checks
            active_result = exec_command(
                conn, "systemctl is-active docker", sudo=True, pty=False
            )
            status_info["backend.is_running"] = active_result == "active"
            status_info["docker.is_running"] = active_result == "active"

            enabled_result = exec_command(
                conn, "systemctl is-enabled docker", sudo=True, pty=False
            )
            status_info["docker.is_enabled"] = enabled_result == "enabled"

            if status_info["docker.is_running"]:
                # Get Docker version
                try:
                    version_json_str = exec_command(
                        conn,
                        "docker version --format '{{json .}}'",
                        sudo=True,
                        pty=False,
                    )
                    if version_json_str:
                        status_info["docker.version"] = json.loads(version_json_str)
                    else:
                        status_info["docker.version"] = "Error retrieving version"
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Docker version JSON: {e}")
                    status_info["docker.version"] = "Error parsing version JSON"
                except Exception as e:
                    logger.error(f"Error getting Docker version: {e}")
                    status_info["docker.version"] = "Error retrieving version"

                # Get list of all containers (running and stopped)
                try:
                    containers_json_str = exec_command(
                        conn, "docker ps -a --format '{{json .}}'", sudo=True, pty=False
                    )
                    if containers_json_str:
                        # Each line is a JSON object, so we need to parse them individually
                        containers_list = []
                        for line in containers_json_str.strip().split("\n"):
                            if line:  # Ensure line is not empty
                                containers_list.append(json.loads(line))
                        status_info["docker.containers"] = containers_list
                    else:
                        status_info["docker.containers"] = []  # No containers or error
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Docker containers JSON: {e}")
                    status_info["docker.containers"] = "Error parsing containers JSON"
                except Exception as e:
                    logger.error(f"Error getting Docker containers: {e}")
                    status_info["docker.containers"] = "Error retrieving containers"
        return status_info

    def start_backend_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl start docker", sudo=True)

    def stop_backend_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl stop docker", sudo=True)
