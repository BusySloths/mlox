import re
import logging

from dataclasses import dataclass, field
from typing import Dict, Any

from mlox.servers.ubuntu.docker import UbuntuDockerServer
from mlox.remote import exec_command

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class UbuntuK3sServer(UbuntuDockerServer):
    controller_url: str = field(
        default="", metadata={"help": "Optional URL of the k3s controller node"}
    )
    controller_token: str = field(
        default="", metadata={"help": "Optional token for the k3s controller node"}
    )

    def __post_init__(self):
        super().__post_init__()
        if len(self.controller_url) > 6 and len(self.controller_token) > 6:
            self.backend = ["kubernetes-agent", "k3s-agent"]
        else:
            self.backend = ["kubernetes", "k3s"]

    def setup_backend(self):
        self.state = "starting"

        # Controller URL Template: https://<controller-ip>:6443
        agent_str = ""
        if len(self.controller_url) > 6 and len(self.controller_token) > 6:
            agent_str = (
                f"K3S_URL={self.controller_url} K3S_TOKEN={self.controller_token} "
            )

        with self.get_server_connection() as conn:
            exec_command(
                conn,
                f"curl -sfL https://get.k3s.io | {agent_str}sh -s -",
                sudo=True,
                pty=True,
            )
            exec_command(conn, "systemctl status k3s", sudo=True)
            exec_command(conn, "kubectl get nodes", sudo=True)
            exec_command(conn, "kubectl version", sudo=True)

            # Install Helm CLI
            logger.info("Installing Helm CLI...")
            exec_command(
                conn,
                "curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3",
                sudo=False,
            )
            exec_command(conn, "chmod 700 get_helm.sh", sudo=False)
            # The get_helm.sh script typically installs to /usr/local/bin/helm, which might require sudo.
            exec_command(conn, "./get_helm.sh", sudo=True)
            exec_command(
                conn, "helm version", sudo=True
            )  # Verify helm installation, using sudo to match kubectl checks
            logger.info("Helm CLI installed successfully.")
            self.state = "running"

    def teardown_backend(self) -> None:
        self.state = "shutdown"
        """Uninstalls k3s using the official uninstall scripts."""
        uninstalled = False
        with self.get_server_connection() as conn:
            # Try server uninstall script first
            logger.info("Attempting to uninstall k3s server...")
            try:
                # Check if server uninstall script exists
                if conn.run("test -f /usr/local/bin/k3s-uninstall.sh", warn=True).ok:
                    exec_command(
                        conn, "/usr/local/bin/k3s-uninstall.sh", sudo=True, pty=True
                    )
                    logger.info("k3s server uninstalled successfully.")
                    uninstalled = True
                else:
                    logger.info("/usr/local/bin/k3s-uninstall.sh not found.")
            except Exception as e:
                logger.warning(
                    f"Failed to run k3s-uninstall.sh or script not present: {e}"
                )

            if not uninstalled:
                # Try agent uninstall script if server uninstall didn't run or wasn't applicable
                logger.info("Attempting to uninstall k3s agent...")
                try:
                    if conn.run(
                        "test -f /usr/local/bin/k3s-agent-uninstall.sh", warn=True
                    ).ok:
                        exec_command(
                            conn,
                            "/usr/local/bin/k3s-agent-uninstall.sh",
                            sudo=True,
                            pty=True,
                        )
                        logger.info("k3s agent uninstalled successfully.")
                        uninstalled = True
                    else:
                        logger.info("/usr/local/bin/k3s-agent-uninstall.sh not found.")
                except Exception as e:
                    logger.warning(
                        f"Failed to run k3s-agent-uninstall.sh or script not present: {e}"
                    )

            if not uninstalled:
                logger.warning(
                    "Neither k3s server nor agent uninstall scripts were found or ran successfully. k3s might still be present."
                )
            self.state = "no-backend"

    def get_backend_status(self) -> Dict[str, Any]:
        backend_info: Dict[str, Any] = {}
        with self.get_server_connection() as conn:
            # Check k3s status
            res = exec_command(conn, "systemctl is-active k3s", sudo=True, pty=False)
            if res is None:
                backend_info["k3s.is_running"] = False
            else:
                backend_info["k3s.is_running"] = True
            backend_info["backend.is_running"] = backend_info["k3s.is_running"]

            # Check k3s-agent status
            res = exec_command(
                conn, "systemctl is-active k3s-agent", sudo=True, pty=False
            )
            if res is None:
                backend_info["k3s-agent.is_running"] = False
            else:
                backend_info["k3s-agent.is_running"] = True
            # If k3s is running, get node status
            try:
                res = exec_command(
                    conn,
                    "cat /var/lib/rancher/k3s/server/node-token",
                    sudo=True,
                    pty=True,
                )
                backend_info["k3s.token"] = res.split("password: ")[1].strip()
                node_output = exec_command(
                    conn, "kubectl get nodes -o wide", sudo=True, pty=False
                )
                # Parse kubectl get nodes output (simple parsing assuming standard format)
                nodes = []
                lines = node_output.strip().split("\n")
                if len(lines) > 1:  # Skip header line
                    header_parts = lines[0].split()
                    print(header_parts)
                    for line in lines[1:]:
                        parts = re.split(r"\s{2,}", line)
                        print(parts)
                        if len(parts) >= 2:
                            res = {header_parts[i]: parts[i] for i in range(len(parts))}
                            nodes.append(res)
                backend_info["k3s.nodes"] = nodes
            except Exception as e:
                logger.warning(f"Could not get k3s node info: {e}")
                backend_info["k3s.nodes"] = "Error retrieving node info"
        return backend_info

    def start_backend_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl start k3s", sudo=True)

    def stop_backend_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl stop k3s", sudo=True)
