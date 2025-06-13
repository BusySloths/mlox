import re
import logging
import tempfile
import importlib
import logging

import time  # Added for retry delay
import json  # For parsing docker command JSON output
from dataclasses import dataclass, field
from abc import abstractmethod, ABC
from typing import (
    Dict,
    Optional,
    List,
    Tuple,
    Literal,
    Any,
    Protocol,
    ContextManager,
    TYPE_CHECKING,
)

from fabric import Connection  # type: ignore
from paramiko.ssh_exception import (  # type: ignore
    SSHException,
    AuthenticationException,
    NoValidConnectionsError,
)
import socket

from mlox.utils import generate_password
from mlox.remote import (
    open_connection,
    close_connection,
    exec_command,
    fs_read_file,
    fs_find_and_replace,
    fs_append_line,
    fs_create_dir,
    fs_delete_dir,
    sys_add_user,
    # sys_get_distro_info,
    sys_user_id,
)

if TYPE_CHECKING:
    # Forward declaration for type hinting if ServerConnection is used in Protocol before definition
    pass

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ServerConnection:
    credentials: Dict
    _conn: Connection | None = field(default=None, init=False)
    _tmp_dir: Optional[tempfile.TemporaryDirectory] = field(default=None, init=False)
    retries: int = field(default=3, kw_only=True)  # Number of connection attempts
    retry_delay: int = field(
        default=5, kw_only=True
    )  # Delay between retries in seconds

    # Allow __init__ to accept credentials only, or also retry parameters
    def __init__(self, credentials: Dict, retries: int = 3, retry_delay: int = 5):
        self.credentials = credentials
        self.retries = retries
        self.retry_delay = retry_delay

    def __enter__(self):
        current_attempt = 0
        host = self.credentials.get("host", "N/A")

        # Specific exceptions that are genuinely worth retrying for connection
        RETRYABLE_EXCEPTIONS_FOR_CONNECTION = (
            socket.timeout,  # General socket timeout
            NoValidConnectionsError,  # If all resolved IPs for a host fail connection
            EOFError,  # Can sometimes be transient network drop
            # SSHException can be broad; if specific transient SSH errors are known, list them.
            # Avoid retrying AuthenticationException or issues due to bad host configuration here.
        )

        while current_attempt <= self.retries:
            try:
                # Step 1: Get the Connection object (doesn't connect yet)
                raw_conn, self_tmp_dir_obj = open_connection(self.credentials)
                self._tmp_dir = self_tmp_dir_obj  # Store the TemporaryDirectory object

                # Step 2: Explicitly open the connection to trigger actual network attempt
                logger.debug(f"Attempting to open connection to {host}...")
                raw_conn.open()
                logger.debug(
                    f"Connection opened to {host}. Verifying by running a simple command."
                )

                # Step 3: (Optional but recommended) Verify with a no-op command
                # This ensures the connection is truly usable.
                result = raw_conn.run("true", hide=True, warn=True, pty=False)
                if not result.ok:
                    error_message = (
                        f"Connection to {host} opened, but verification command 'true' failed. "
                        f"Exit code: {result.return_code}, stderr: {result.stderr.strip()}"
                    )
                    logger.error(error_message)
                    # Treat this as a connection failure for retry purposes
                    # Using SSHException as a generic wrapper for this verification failure
                    raise SSHException(error_message)

                self._conn = raw_conn  # Assign to self._conn only after successful open and verification

                logging.info(
                    f"Successfully opened and verified connection to {host} on attempt {current_attempt + 1}"
                )
                return self._conn
            except (
                RETRYABLE_EXCEPTIONS_FOR_CONNECTION
            ) as e:  # Catch only specified retryable exceptions
                logging.warning(
                    f"Failed to open connection to {host} (attempt {current_attempt + 1}/{self.retries + 1}): {type(e).__name__} - {e}"
                )
                if current_attempt == self.retries:
                    logging.error(f"Max connection retries reached for {host}.")
                    raise
                logging.info(f"Retrying connection in {self.retry_delay} seconds...")
                if self._tmp_dir:  # Clean up temp dir if connection failed partway
                    # Pass None for conn as it might be in a bad state or not fully initialized
                    close_connection(None, self._tmp_dir)
                    self._tmp_dir = (
                        None  # Reset tmp_dir to avoid trying to clean it again
                    )
                time.sleep(self.retry_delay)
                current_attempt += 1
            except (
                socket.gaierror,
                AuthenticationException,
            ) as e:  # Non-retryable errors
                logging.error(
                    f"Non-retryable error connecting to {host}: {type(e).__name__} - {e}"
                )
                if self._tmp_dir:
                    close_connection(None, self._tmp_dir)
                    self._tmp_dir = None
                raise  # Re-raise immediately, do not retry
            except (
                Exception
            ) as e:  # Catch any other unexpected errors during connection setup
                logging.error(
                    f"Unexpected error during connection attempt to {host}: {type(e).__name__} - {e}"
                )
                if self._tmp_dir:
                    close_connection(None, self._tmp_dir)
                    self._tmp_dir = None
                raise  # Re-raise immediately

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._conn:
                close_connection(self._conn, self._tmp_dir)
                logging.info(f"Successfully closed connection to {self._conn.host}")
            if exc_type is not None:
                logging.exception(
                    f"An exception occurred during connection usage: {exc_val}"
                )
                # Consider more specific exception handling here based on needs
        except Exception as e:
            logging.error(f"Error during connection cleanup: {e}")
            # Decide whether to re-raise the cleanup exception or let it go (depends on context)


@dataclass
class MloxUser:
    name: str
    pw: str
    uid: int | str = field(default=1000, init=False)
    home: str
    ssh_passphrase: str
    ssh_pub_key: str = field(default="", init=False)


@dataclass
class RemoteUser:
    ssh_passphrase: str
    ssh_key: str = field(default="", init=False)
    ssh_pub_key: str = field(default="", init=False)


@dataclass
class AbstractServer(ABC):
    ip: str
    root: str
    root_pw: str
    port: str = field(default="22")

    mlox_user: MloxUser | None = field(default=None, init=False)
    remote_user: RemoteUser | None = field(default=None, init=False)

    def get_server_connection(self, force_root: bool = False) -> ServerConnection:
        # 3 ways to connect:
        # 1. root user with password (only for initial setup, should be disabled asap)
        # 2. mlox user name with password (should be disabled asap)
        # 3. mlox user SSH with remote user SSH credentials (recommended)
        credentials = {
            "host": self.ip,
            "port": self.port,
            "user": self.mlox_user.name if self.mlox_user else self.root,
            "pw": self.mlox_user.pw if self.mlox_user else self.root_pw,
        }
        if self.remote_user:
            credentials.update(
                {
                    "public_key": self.remote_user.ssh_pub_key,
                    "private_key": self.remote_user.ssh_key,
                    "passphrase": self.remote_user.ssh_passphrase,
                }
            )
        if force_root:
            credentials = {
                "host": self.ip,
                "port": self.port,
                "user": self.root,
                "pw": self.root_pw,
            }

        return ServerConnection(credentials)

    def get_mlox_user_template(self) -> MloxUser:
        mlox_name_postfix = generate_password(5, with_punctuation=False)
        mlox_pw = generate_password(20)
        mlox_passphrase = generate_password(20)
        mlox_user = MloxUser(
            name=f"mlox_{mlox_name_postfix}",
            pw=mlox_pw,
            home=f"/home/mlox_{mlox_name_postfix}",
            ssh_passphrase=mlox_passphrase,
        )
        return mlox_user

    def get_remote_user_template(self) -> RemoteUser:
        remote_passphrase = generate_password(20)
        return RemoteUser(ssh_passphrase=remote_passphrase)

    def test_connection(self) -> bool:
        verified = False
        try:
            with self.get_server_connection() as conn:
                verified = True
            print(f"Public key SSH login verified={verified}.")
        except Exception as e:
            print(f"Failed to login via SSH with public key: {e}")
        return verified

    @abstractmethod
    def update(self) -> None:
        pass

    @abstractmethod
    def install_packages(self) -> None:
        pass

    @abstractmethod
    def add_mlox_user(self) -> None:
        pass

    @abstractmethod
    def setup_users(self) -> None:
        pass

    @abstractmethod
    def enable_password_authentication(self) -> None:
        pass

    @abstractmethod
    def disable_password_authentication(self) -> None:
        pass

    @abstractmethod
    def get_server_info(self) -> Dict[str, str | int | float]:
        pass

    # GIT
    @abstractmethod
    def git_clone(self, repo_url: str, path: str) -> None:
        pass

    @abstractmethod
    def git_pull(self, path: str) -> None:
        pass

    @abstractmethod
    def git_remove(self, path: str) -> None:
        pass

    # DOCKER
    @abstractmethod
    def setup_docker(self) -> None:
        pass

    @abstractmethod
    def teardown_docker(self) -> None:
        pass

    @abstractmethod
    def get_docker_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def start_docker_runtime(self) -> None:
        pass

    @abstractmethod
    def stop_docker_runtime(self) -> None:
        pass

    # KUBERNETES
    @abstractmethod
    def setup_kubernetes(
        self, controller_url: str | None = None, controller_token: str | None = None
    ):
        pass

    @abstractmethod
    def teardown_kubernetes(self) -> None:
        pass

    @abstractmethod
    def get_kubernetes_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def start_kubernetes_runtime(self) -> None:
        pass

    @abstractmethod
    def stop_kubernetes_runtime(self) -> None:
        pass


@dataclass
class Ubuntu(AbstractServer):
    _specs: Dict[str, str | int | float] | None = field(default=None, init=False)

    def update(self):
        with self.get_server_connection() as conn:
            exec_command(conn, "dpkg --configure -a", sudo=True)
            exec_command(conn, "apt-get update", sudo=True)
            exec_command(conn, "apt-get -y upgrade", sudo=True)
            print("Done updating")

    def install_packages(self):
        with self.get_server_connection() as conn:
            exec_command(conn, "dpkg --configure -a", sudo=True)
            exec_command(
                conn, "apt-get -y install mc", sudo=True
            )  # why does it not find mc??
            exec_command(conn, "apt-get -y install git", sudo=True)
            exec_command(conn, "apt-get -y install zsh", sudo=True)

    def get_server_info(self) -> Dict[str, str | int | float]:
        if self._specs:
            return self._specs

        cmd = """
                cpu_count=$(lscpu | grep "^CPU(s):" | awk '{print $2}')
                ram_gb=$(free -m | grep Mem | awk '{printf "%.0f", $2/1024}')
                storage_gb=$(df -h / | awk 'NR==2 {print $2}' | sed 's/G//')
                echo "$cpu_count,$ram_gb,$storage_gb" 
            """

        system_info = None
        hardware_info = None
        with self.get_server_connection() as conn:
            hardware_info = exec_command(conn, cmd, sudo=True)
            system_info = sys_get_distro_info(conn)

        hardware_info = list(map(float, str(hardware_info).split(",")))
        info: Dict[str, str | int | float] = dict()

        info = dict(
            {
                "cpu_count": float(hardware_info[0]),
                "ram_gb": float(hardware_info[1]),
                "storage_gb": float(hardware_info[2]),
            }
        )
        if system_info is not None:
            info.update(system_info)

        print(f"VPS information: {info}")
        self._specs = info
        return info

    def add_mlox_user(self) -> None:
        mlox_user = self.get_mlox_user_template()
        # 1. add mlox user
        with self.get_server_connection() as conn:
            print(
                f"Add user: {mlox_user.name} with password {mlox_user.pw}. Create home dir and add to sudo group."
            )
            sys_add_user(
                conn, mlox_user.name, mlox_user.pw, with_home_dir=True, sudoer=True
            )
        self.mlox_user = mlox_user

    def setup_users(self) -> None:
        remote_user = self.get_remote_user_template()
        if self.mlox_user is None:
            logging.warning(
                "MLOX user did not exist before calling setup_users. Trying again to add user..."
            )
            self.add_mlox_user()

        if not self.mlox_user:
            logging.error("MLOX user still missing after retries. ")
            return

        # 2. generate ssh keys for mlox and remote user
        with self.get_server_connection() as conn:
            # 1. create .ssh dir
            print(f"Create .ssh dir for user {self.mlox_user.name}.")
            command = "mkdir -p ~/.ssh; chmod 700 ~/.ssh"
            exec_command(conn, command)

            # 2. generate rsa keys for remote user
            print(f"Generate RSA keys for remote user on server {self.ip}.")
            command = f"cd {self.mlox_user.home}/.ssh; rm id_rsa*; ssh-keygen -b 4096 -t rsa -f id_rsa -N {remote_user.ssh_passphrase}"
            exec_command(conn, command, sudo=False)

            # 3. read pub and private keys and store to remote user
            remote_user.ssh_pub_key = fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa.pub", format="string"
            ).strip()
            remote_user.ssh_key = fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa", format="string"
            ).strip()
            print(f"Remote user public key: {remote_user.ssh_pub_key}")
            print(f"Remote user private key: {remote_user.ssh_key}")
            print(f"Remote user passphrase: {remote_user.ssh_passphrase}")

            # 4. generate rsa keys for mlox user
            print(f"Generate RSA keys for {self.mlox_user.name} on server {self.ip}.")
            command = f"cd {self.mlox_user.home}/.ssh; rm id_rsa*; ssh-keygen -b 4096 -t rsa -f id_rsa -N {self.mlox_user.ssh_passphrase}"
            exec_command(conn, command, sudo=False)

            # 5. read pub and private keys and store to mlox user
            self.mlox_user.ssh_pub_key = fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa.pub", format="string"
            ).strip()

            # 6. add remote user public key to authorized_keys
            fs_append_line(
                conn,
                f"{self.mlox_user.home}/.ssh/authorized_keys",
                remote_user.ssh_pub_key,
            )

            # 7. get user system id
            self.mlox_user.uid = sys_user_id(conn)

        self.remote_user = remote_user
        if not self.test_connection():
            print("Uh oh, something went while setting up the SSH connection.")
        else:
            print(
                f"User {self.mlox_user.name} created with password {self.mlox_user.pw}."
            )

    def disable_password_authentication(self):
        with self.get_server_connection() as conn:
            # 1. uncomment if comment out
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "#PasswordAuthentication",
                "PasswordAuthentication",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "#PermitRootLogin",
                "PermitRootLogin",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "#PubkeyAuthentication",
                "PubkeyAuthentication",
                sudo=True,
            )

            # 2. Disable includes
            fs_find_and_replace(
                conn, "/etc/ssh/sshd_config", "Include", "#Include", sudo=True
            )

            # 2. change to desired value
            fs_find_and_replace(
                conn, "/etc/ssh/sshd_config", "UsePAM yes", "UsePAM no", sudo=True
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "PasswordAuthentication yes",
                "PasswordAuthentication no",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "KeyboardInteractiveAuthentication yes",
                "KeyboardInteractiveAuthentication no",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "PubkeyAuthentication no",
                "PubkeyAuthentication yes",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "X11Forwarding yes",
                "X11Forwarding no",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "AllowTcpForwarding yes",
                "AllowTcpForwarding no",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "PermitRootLogin yes",
                "PermitRootLogin no",
                sudo=True,
            )
            exec_command(conn, "systemctl restart ssh", sudo=True)
            exec_command(conn, "systemctl reload ssh", sudo=True)

    def enable_password_authentication(self):
        with self.get_server_connection() as conn:
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "#PasswordAuthentication",
                "PasswordAuthentication",
                sudo=True,
            )
            fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "PasswordAuthentication no",
                "PasswordAuthentication yes",
                sudo=True,
            )
            exec_command(conn, "systemctl restart ssh", sudo=True)
            exec_command(conn, "systemctl reload ssh", sudo=True)

    # GIT
    def git_clone(self, repo_url: str, path: str) -> None:
        with self.get_server_connection() as conn:
            if self.mlox_user:
                abs_path = f"{self.mlox_user.home}/{path}"
                fs_create_dir(conn, abs_path)
                exec_command(conn, f"cd {path}; git clone {repo_url}", sudo=False)

    def git_pull(self, abs_path: str) -> None:
        # TODO check if the path exists, rn we assume the path is valid
        with self.get_server_connection() as conn:
            if self.mlox_user:
                # abs_path = f"{self.mlox_user.home}/{repo_root_path}"
                exec_command(conn, f"cd {abs_path}; git pull", sudo=False)

    def git_remove(self, path: str) -> None:
        with self.get_server_connection() as conn:
            fs_delete_dir(conn, path)

    # DOCKER
    def setup_docker(self) -> None:
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

    def teardown_docker(self) -> None:
        """Uninstalls Docker Engine and related packages."""
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

    def get_docker_status(self) -> Dict[str, Any]:
        status_info: Dict[str, Any] = {}
        with self.get_server_connection() as conn:
            # Check Docker status
            # systemctl is-active returns 0 for active, non-zero otherwise
            # pty=False is generally better for non-interactive status checks
            active_result = exec_command(
                conn, "systemctl is-active docker", sudo=True, pty=False
            )
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

    def start_docker_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl start docker", sudo=True)

    def stop_docker_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl stop docker", sudo=True)

    # KUBERNETES
    def setup_kubernetes(
        self, controller_url: str | None = None, controller_token: str | None = None
    ):
        # Controller URL Template: https://<controller-ip>:6443
        agent_str = ""
        if controller_url and controller_token:
            agent_str = f"K3S_URL={controller_url} K3S_TOKEN={controller_token} "

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

    def teardown_kubernetes(self) -> None:
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

    def get_kubernetes_status(self) -> Dict[str, Any]:
        backend_info: Dict[str, Any] = {}
        with self.get_server_connection() as conn:
            # Check k3s status
            res = exec_command(conn, "systemctl is-active k3s", sudo=True, pty=False)
            if res is None:
                backend_info["k3s.is_running"] = False
            else:
                backend_info["k3s.is_running"] = True
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

    def start_kubernetes_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl start k3s", sudo=True)

    def stop_kubernetes_runtime(self) -> None:
        with self.get_server_connection() as conn:
            exec_command(conn, "systemctl stop k3s", sudo=True)


@dataclass
class ConfigurableServer(AbstractServer):
    script_setup: List[str | List[str]] = field(default_factory=list)
    script_update: List[str | List[str]] = field(default_factory=list)
    script_test: List[str | List[str]] = field(default_factory=list)
    script_generate_ssh_keys: List[str | List[str]] = field(default_factory=list)

    def setup(self) -> None:
        pass

    def generate_ssh_keys(self) -> None:
        with self.get_server_connection() as conn:
            for cmd in self.script_generate_ssh_keys:
                execute_command(conn, cmd)
        print("Done updating")

    def update(self) -> None:
        # with self.get_server_connection() as conn:
        #     for cmd in self.script_update:
        #         exec_command(conn, cmd, sudo=True)
        #     print("Done updating")

        with self.get_server_connection() as conn:
            for cmd in self.script_test:
                execute_command(conn, cmd)
        print("Done updating")

    def install_packages(self) -> None:
        pass

    def get_server_info(self) -> Dict[str, str | int | float]:
        return dict()


def sys_get_distro_info(conn) -> Optional[Dict[str, str]]:
    """
    Attempts to get the Linux distribution name and version.

    Tries reading /etc/os-release first, then falls back to lsb_release.

    Returns:
        A dictionary containing info like 'name', 'version', 'id', 'pretty_name'
        or None if information couldn't be retrieved reliably.
    """
    info = {}
    try:
        # Try /etc/os-release first using fs_read_file
        content = fs_read_file(conn, "/etc/os-release", format="string")
        # Parse the key="value" or key=value format
        for line in content.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip().lower()  # Use lower-case keys
                # Remove surrounding quotes if present
                value = value.strip().strip('"')
                info[key] = value
        # Add a 'version' key, preferring 'version_id' if available
        if "version_id" in info:
            info["version"] = info["version_id"]
        elif "version" in info:
            # Keep existing 'version' if 'version_id' is not present
            pass
        # If we got at least a name or pretty_name, return it
        if "name" in info or "pretty_name" in info:
            logger.info(f"Distro info from /etc/os-release: {info}")
            return info
    except Exception as e:
        logger.warning(f"Could not read /etc/os-release: {e}. Trying lsb_release.")
        info = {}  # Reset info if os-release failed or was insufficient

    # Fallback to lsb_release if /etc/os-release didn't work
    try:
        # Use lsb_release -a and parse common fields
        lsb_output = exec_command(conn, "lsb_release -a", sudo=False, pty=False)
        if lsb_output:
            for line in lsb_output.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = (
                        key.strip().lower().replace(" ", "_")
                    )  # e.g., 'distributor id' -> 'distributor_id'
                    value = value.strip()
                    if key == "distributor_id":
                        info["id"] = value
                        info["name"] = value  # Use id as name
                    if key == "release":
                        info["version"] = value
                    if key == "description":
                        info["pretty_name"] = value
                    if key == "codename":
                        info["codename"] = value
            if "name" in info and "version" in info:
                logger.info(f"Distro info from lsb_release: {info}")
                return info
    except Exception as e:
        logger.error(f"Could not get distro info using lsb_release: {e}")

    logger.error("Unable to determine Linux distribution info.")
    return None


def execute_command(conn, cmd: List | str):
    if isinstance(cmd, str):
        # Type 1: single CMD executed as sudo
        exec_command(conn, cmd, sudo=True)
    if isinstance(cmd, list):
        if isinstance(cmd[0], bool):
            # Type 2: [Sudo True/False, CMD, Descr]
            exec_command(conn, cmd[1], sudo=cmd[0])
        else:
            # Type 3: Function call with arguments
            func_name = cmd[0]
            module_name = "mlox.remote"
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
            args = cmd[1:]
            print(f"Execute CMD: {func_name} with args: {args}")
            if args:
                func(conn, *args)
            else:
                func(conn)
