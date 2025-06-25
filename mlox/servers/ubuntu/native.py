import logging

from dataclasses import dataclass, field
from typing import Dict, Any

from mlox.server import AbstractServer, AbstractGitServer, sys_get_distro_info
from mlox.remote import (
    exec_command,
    fs_read_file,
    fs_find_and_replace,
    fs_append_line,
    fs_create_dir,
    fs_delete_dir,
    sys_add_user,
    sys_user_id,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class UbuntuNativeServer(AbstractServer, AbstractGitServer):
    _specs: Dict[str, str | int | float] | None = field(default=None, init=False)

    def __post_init__(self):
        self.backend = ["native"]

    def setup(self):
        if self.state != "un-initialized":
            logging.error("Can not initialize an already initialized server.")
            return
        self.state = "starting"
        self.update()
        self.install_packages()
        self.update()
        self.add_mlox_user()
        self.setup_users()
        self.disable_password_authentication()
        self.setup_backend()
        self.state = "running"

    def teardown(self):
        self.state = "shutdown"
        self.teardown_backend()
        # self.enable_password_authentication()
        self.state = "no-backend"

    def enable_debug_access(self) -> None:
        self.enable_password_authentication()

    def disable_debug_access(self) -> None:
        self.disable_password_authentication()

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

        host_info = ""
        system_info = None
        hardware_info = None
        with self.get_server_connection() as conn:
            hardware_info = exec_command(conn, cmd, sudo=True)
            system_info = sys_get_distro_info(conn)
            host_info = exec_command(conn, f"host {conn.host}", sudo=False)

        if len(host_info) > 3 and " " in host_info:
            host_info = host_info[:-1].split(" ")[-1]
        else:
            host_info = "unknown"

        hardware_info = list(map(float, str(hardware_info).split(",")))
        info: Dict[str, str | int | float] = dict()

        info = dict(
            {
                "cpu_count": float(hardware_info[0]),
                "ram_gb": float(hardware_info[1]),
                "storage_gb": float(hardware_info[2]),
                "host": host_info,
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
    def git_clone(self, repo_url: str, abs_path: str) -> None:
        with self.get_server_connection() as conn:
            if self.mlox_user:
                fs_create_dir(conn, abs_path)
                exec_command(conn, f"cd {abs_path}; git clone {repo_url}", sudo=False)

    def git_pull(self, abs_path: str) -> None:
        # TODO check if the path exists, rn we assume the path is valid
        with self.get_server_connection() as conn:
            if self.mlox_user:
                # abs_path = f"{self.mlox_user.home}/{repo_root_path}"
                exec_command(conn, f"cd {abs_path}; git pull", sudo=False)

    def git_remove(self, abs_path: str) -> None:
        with self.get_server_connection() as conn:
            fs_delete_dir(conn, abs_path)

    # NATIVE BACKEND
    def setup_backend(self) -> None:
        logger.info("Native backend setup done.")
        self.state = "running"

    def teardown_backend(self) -> None:
        logger.info("Native backend taerdown done.")
        self.state = "no-backend"

    def get_backend_status(self) -> Dict[str, Any]:
        status_info: Dict[str, Any] = {}
        return status_info

    def start_backend_runtime(self) -> None:
        logger.info("Native backend start.")

    def stop_backend_runtime(self) -> None:
        logger.info("Native backend stop.")
