import logging
import importlib
import string
import secrets
import json
import tempfile


from dataclasses import dataclass, field, asdict, is_dataclass
from abc import abstractmethod, ABC
from typing import Dict, Optional, List, Tuple, Type, TypeVar, cast, Any
from fabric import Connection  # type: ignore

from mlox.utils import load_dataclass_from_json, save_dataclass_to_json, execute_command
from mlox.remote import (
    get_config,
    open_connection,
    close_connection,
    exec_command,
    fs_copy,
    fs_read_file,
    fs_create_dir,
    fs_find_and_replace,
    fs_create_empty_file,
    fs_append_line,
    sys_user_id,
    sys_add_user,
    docker_up,
    docker_down,
    open_ssh_connection,
)

T = TypeVar("T")

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def tls_setup(conn, ip, path) -> None:
    # copy files to target
    fs_create_dir(conn, path)
    fs_copy(conn, "./stacks/mlox/openssl-san.cnf", f"{path}/openssl-san.cnf")
    fs_find_and_replace(conn, f"{path}/openssl-san.cnf", "<MY_IP>", f"{ip}")
    # certificates
    exec_command(conn, f"cd {path}; openssl genrsa -out key.pem 2048")
    exec_command(
        conn,
        f"cd {path}; openssl req -new -key key.pem -out server.csr -config openssl-san.cnf",
    )
    exec_command(
        conn,
        f"cd {path}; openssl x509 -req -in server.csr -signkey key.pem -out cert.pem -days 365 -extensions req_ext -extfile openssl-san.cnf",
    )
    exec_command(conn, f"chmod u=rw,g=rw,o=rw {path}/key.pem")


def generate_password(length: int = 10, with_punctuation: bool = False) -> str:
    """
    Generate a random password with at least 3 digits, 1 uppercase letter, and 1 lowercase letter.
    :param length: Length of the password
    :param with_punctuation: Include punctuation characters in the password
    :return: Generated password
    """
    if length < 5:
        raise ValueError("Password length must be at least 5 characters.")
    alphabet = string.ascii_letters + string.digits
    if with_punctuation:
        alphabet = alphabet + string.punctuation
    while True:
        password = "".join(secrets.choice(alphabet) for i in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and sum(c.isdigit() for c in password) >= 3
        ):
            break
    return password


@dataclass
class AbstractService(ABC):
    target_path: str
    target_docker_script: str = field(default="docker-compose.yaml", init=False)
    target_docker_env: str = field(default="service.env", init=False)

    is_running: bool = field(default=False, init=False)
    is_installed: bool = field(default=False, init=False)

    service_url: str = field(default="", init=False)

    @abstractmethod
    def setup(self, conn) -> None:
        pass

    def teardown(self, conn) -> None:
        pass

    def spin_up(self, conn) -> bool:
        docker_up(
            conn,
            f"{self.target_path}/{self.target_docker_script}",
            f"{self.target_path}/{self.target_docker_env}",
        )
        self.is_running = True
        return True

    def spin_down(self, conn) -> bool:
        docker_down(conn, f"{self.target_path}/{self.target_docker_script}")
        self.is_running = False
        return True

    @abstractmethod
    def check(self) -> Dict:
        pass


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
    uid: int = field(default=1000, init=False)
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
    port: str = field(default="22", init=False)

    root: str
    root_pw: str

    mlox_user: MloxUser | None = field(default=None, init=False)
    remote_user: RemoteUser | None = field(default=None, init=False)

    services: List[AbstractService] = field(default_factory=list, init=False)
    setup_complete: bool = field(default=False, init=False)

    def add_service(self, service: AbstractService) -> None:
        self.services.append(service)

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
    def install_kubernetes(self) -> None:
        pass

    @abstractmethod
    def setup_users(self) -> None:
        pass

    @abstractmethod
    def disable_password_authentication(self) -> None:
        pass

    @abstractmethod
    def get_server_info(self) -> Tuple[int, float, float]:
        pass


@dataclass
class Ubuntu(AbstractServer):
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

    def install_kubernetes(self):
        with self.get_server_connection() as conn:
            exec_command(
                conn, "curl -sfL https://get.k3s.io | sh -s -", sudo=True, pty=True
            )
            exec_command(conn, "systemctl status k3s", sudo=True)
            exec_command(conn, "kubectl get nodes", sudo=True)
            exec_command(conn, "kubectl version", sudo=True)

    def get_server_info(self) -> Tuple[int, float, float]:
        cmd = """
                cpu_count=$(lscpu | grep "^CPU(s):" | awk '{print $2}')
                ram_gb=$(free -m | grep Mem | awk '{printf "%.0f", $2/1024}')
                storage_gb=$(df -h / | awk 'NR==2 {print $2}' | sed 's/G//')
                echo "$cpu_count,$ram_gb,$storage_gb" 
            """

        info = None
        with self.get_server_connection() as conn:
            info = exec_command(conn, cmd, sudo=True)
        print(str(info).split(","))
        info = list(map(float, str(info).split(",")))
        return int(info[0]), float(info[1]), float(info[2])

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

        self.remote_user = remote_user
        if not self.test_connection():
            print(f"Uh oh, something went while setting up the SSH connection.")
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
        conn = open_ssh_connection(self.ip, self.root, self.root_pw, self.port)
        for cmd in self.script_generate_ssh_keys:
            execute_command(conn, cmd)
        print("Done updating")
        close_connection(conn)

    def update(self) -> None:
        # with self.get_server_connection() as conn:
        #     for cmd in self.script_update:
        #         exec_command(conn, cmd, sudo=True)
        #     print("Done updating")

        conn = open_ssh_connection(self.ip, self.root, self.root_pw, self.port)
        for cmd in self.script_test:
            execute_command(conn, cmd)
        print("Done updating")
        close_connection(conn)

    def install_packages(self) -> None:
        pass

    def get_server_info(self) -> Tuple[int, float, float]:
        return 0, 0, 0


if __name__ == "__main__":
    # print(generate_password(20))
    # print(generate_password(5, with_punctuation=False))

    server = load_dataclass_from_json("/test_server.json")

    server.update()
    # server.disable_password_authentication()
    # server.install_docker()

    # server.install_kubernetes()
    # server.test_connection()
    # with server.get_server_connection() as conn:
    #     exec_command(conn, "ls -la", sudo=True)
