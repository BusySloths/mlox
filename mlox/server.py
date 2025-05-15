import re
import logging
import tempfile
import importlib
import logging

from dataclasses import dataclass, field
from abc import abstractmethod, ABC
from typing import Dict, Optional, List, Tuple, Literal, Any
from fabric import Connection  # type: ignore

from mlox.utils import generate_password
from mlox.remote import (
    open_connection,
    close_connection,
    exec_command,
    fs_read_file,
    fs_find_and_replace,
    fs_append_line,
    sys_add_user,
    # sys_get_distro_info,
    sys_user_id,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ServerConnection:
    credentials: Dict
    _conn: Connection | None = field(default=None, init=False)
    _tmp_dir: tempfile.TemporaryDirectory | None = field(default=None, init=False)

    def __init__(self, credentials: Dict):
        self.credentials = credentials

    def __enter__(self):
        try:
            self._conn, self._tmp_dir = open_connection(self.credentials)
            logging.info(f"Successfully opened connection to {self._conn.host}")
            return self._conn
        except Exception as e:
            logging.error(f"Failed to open connection: {e}")
            raise  # Re-raise the exception to be handled by the caller

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

    def get_user_templates(self) -> Tuple[RemoteUser, MloxUser]:
        mlox_name_postfix = generate_password(5, with_punctuation=False)
        mlox_pw = generate_password(20)
        mlox_passphrase = generate_password(20)
        remote_passphrase = generate_password(20)

        mlox_user = MloxUser(
            name=f"mlox_{mlox_name_postfix}",
            pw=mlox_pw,
            home=f"/home/mlox_{mlox_name_postfix}",
            ssh_passphrase=mlox_passphrase,
        )
        remote_user = RemoteUser(ssh_passphrase=remote_passphrase)
        return remote_user, mlox_user

    def test_connection(self) -> bool:
        verified = False
        try:
            sc = self.get_server_connection()
            conn, tmpdir = open_connection(sc.credentials)
            close_connection(conn, tmpdir)
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
    def install_docker(self) -> None:
        pass

    @abstractmethod
    def install_kubernetes(
        self, controller_url: str | None = None, controller_token: str | None = None
    ) -> None:
        pass

    @abstractmethod
    def get_kubernetes_token(self) -> str:
        pass

    @abstractmethod
    def switch_backend(
        self, from_backend: Literal["docker", "kubernetes"]
    ) -> Literal["docker", "kubernetes"]:
        pass

    @abstractmethod
    def setup_users(self) -> None:
        pass

    @abstractmethod
    def disable_password_authentication(self) -> None:
        pass

    @abstractmethod
    def get_backend_info(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_server_info(self) -> Dict[str, str | int | float]:
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

    def install_docker(self):
        with self.get_server_connection() as conn:
            exec_command(conn, "apt-get -y install ca-certificates curl", sudo=True)
            exec_command(conn, "install -m 0755 -d /etc/apt/keyrings", sudo=True)
            exec_command(
                conn,
                "curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc",
                sudo=True,
            )
            exec_command(conn, "chmod a+r /etc/apt/keyrings/docker.asc", sudo=True)

            # --- Replace the problematic line ---
            # Old command:
            # exec_command(
            #     conn,
            #     'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list',
            #     sudo=True,
            #     pty=False, # pty=True wouldn't help here either
            # )

            # New command: Use sudo sh -c '...' to run echo and redirection as root
            repo_line = 'deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable'
            # Use double quotes inside the single-quoted sh -c command string
            full_cmd = (
                f"sh -c 'echo \"{repo_line}\" > /etc/apt/sources.list.d/docker.list'"
            )
            exec_command(
                conn, full_cmd, sudo=True, pty=False
            )  # pty=False should be fine
            # --- End of replacement ---

            exec_command(conn, "apt-get update", sudo=True)
            exec_command(
                conn,
                "apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
                sudo=True,
            )
            print("Done installing docker")
            exec_command(conn, "docker --version", sudo=True)

    def switch_backend(
        self, from_backend: Literal["docker", "kubernetes"]
    ) -> Literal["docker", "kubernetes"]:
        with self.get_server_connection() as conn:
            if from_backend == "docker":
                exec_command(conn, "systemctl stop docker", sudo=True)
                exec_command(conn, "systemctl start k3s", sudo=True)
                return "kubernetes"
            else:
                exec_command(conn, "systemctl stop k3s", sudo=True)
                exec_command(conn, "systemctl start docker", sudo=True)
                return "docker"
        return from_backend

    def get_kubernetes_token(self) -> str:
        token = ""
        with self.get_server_connection() as conn:
            res = exec_command(
                conn, f"cat /var/lib/rancher/k3s/server/node-token", sudo=True, pty=True
            )
            token = res.split("password: ")[1].strip()
        return token

    def install_kubernetes(
        self, controller_url: str | None = None, controller_token: str | None = None
    ):
        # Controller URL Template: https://<controller-ip>:6443
        #
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

    def get_backend_info(self) -> Dict[str, Any]:
        """
        Retrieves information about the Docker and k3s backend services.

        Checks if Docker and k3s services are running and, if k3s is active,
        lists the status of its nodes.

        Returns:
            A dictionary containing backend status information.
        """
        backend_info: Dict[str, Any] = {}
        with self.get_server_connection() as conn:
            # Check Docker status
            # systemctl is-active returns 0 for active, non-zero otherwise
            res = exec_command(conn, "systemctl is-active docker", sudo=True, pty=False)
            if res is None:
                backend_info["docker.is_running"] = False
            else:
                backend_info["docker.is_running"] = True

            # Check k3s status
            res = exec_command(conn, "systemctl is-active k3s", sudo=True, pty=False)
            if res is None:
                backend_info["k3s.is_running"] = False
            else:
                backend_info["k3s.is_running"] = True
            # If k3s is running, get node status
            try:
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

    def setup_users(self) -> None:
        remote_user, mlox_user = self.get_user_templates()
        # 1. add mlox user
        with self.get_server_connection() as conn:
            print(
                f"Add user: {mlox_user.name} with password {mlox_user.pw}. Create home dir and add to sudo group."
            )
            sys_add_user(
                conn, mlox_user.name, mlox_user.pw, with_home_dir=True, sudoer=True
            )
        self.mlox_user = mlox_user

        # 2. generate ssh keys for mlox and remote user
        with self.get_server_connection() as conn:
            # 1. create .ssh dir
            print(f"Create .ssh dir for user {mlox_user.name}.")
            command = "mkdir -p ~/.ssh; chmod 700 ~/.ssh"
            exec_command(conn, command)

            # 2. generate rsa keys for remote user
            print(f"Generate RSA keys for remote user on server {self.ip}.")
            command = f"cd {mlox_user.home}/.ssh; rm id_rsa*; ssh-keygen -b 4096 -t rsa -f id_rsa -N {remote_user.ssh_passphrase}"
            exec_command(conn, command, sudo=False)

            # 3. read pub and private keys and store to remote user
            remote_user.ssh_pub_key = fs_read_file(
                conn, f"{mlox_user.home}/.ssh/id_rsa.pub", format="string"
            ).strip()
            remote_user.ssh_key = fs_read_file(
                conn, f"{mlox_user.home}/.ssh/id_rsa", format="string"
            ).strip()
            print(f"Remote user public key: {remote_user.ssh_pub_key}")
            print(f"Remote user private key: {remote_user.ssh_key}")
            print(f"Remote user passphrase: {remote_user.ssh_passphrase}")

            # 4. generate rsa keys for mlox user
            print(f"Generate RSA keys for {mlox_user.name} on server {self.ip}.")
            command = f"cd {mlox_user.home}/.ssh; rm id_rsa*; ssh-keygen -b 4096 -t rsa -f id_rsa -N {mlox_user.ssh_passphrase}"
            exec_command(conn, command, sudo=False)

            # 5. read pub and private keys and store to mlox user
            mlox_user.ssh_pub_key = fs_read_file(
                conn, f"{mlox_user.home}/.ssh/id_rsa.pub", format="string"
            ).strip()

            # 6. add remote user public key to authorized_keys
            fs_append_line(
                conn,
                f"{mlox_user.home}/.ssh/authorized_keys",
                remote_user.ssh_pub_key,
            )

            # 7. get user system id
            self.mlox_user.uid = sys_user_id(conn)

        self.remote_user = remote_user
        if not self.test_connection():
            print("Uh oh, something went while setting up the SSH connection.")
            # self.mlox_user = None
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
