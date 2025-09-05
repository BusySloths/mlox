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
    is_debug_access_enabled: bool = field(default=False, init=False)

    def __post_init__(self):
        super().__post_init__()
        self.backend = ["native"]

    def _apt_wait(self, conn) -> None:
        """Wait until apt/dpkg locks are free to avoid contention errors."""
        wait_cmd = (
            "bash -lc '"
            "while pgrep -x apt >/dev/null || pgrep -x apt-get >/dev/null || "
            "pgrep -x unattended-upgrade >/dev/null || "
            "fuser /var/lib/dpkg/lock >/dev/null 2>&1 || "
            "fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do "
            'echo "[apt-wait] Waiting for other apt/dpkg processes..."; sleep 3; done\''
        )
        try:
            exec_command(conn, wait_cmd, sudo=True, pty=False)
            # Fix partially configured packages if previous runs were interrupted
            exec_command(
                conn,
                "DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true",
                sudo=True,
                pty=False,
            )
        except Exception as e:
            logger.warning(f"apt-wait encountered an issue (continuing): {e}")

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
        self.is_debug_access_enabled = True
        self.enable_password_authentication()

    def disable_debug_access(self) -> None:
        self.is_debug_access_enabled = False
        self.disable_password_authentication()

    def update(self):
        with self.get_server_connection() as conn:
            # Clean up partial states and wait for apt locks to clear
            exec_command(
                conn,
                "DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true",
                sudo=True,
            )
            self._apt_wait(conn)
            exec_command(
                conn,
                "DEBIAN_FRONTEND=noninteractive apt-get -yq -o DPkg::Lock::Timeout=300 update",
                sudo=True,
            )
            self._apt_wait(conn)
            exec_command(
                conn,
                "DEBIAN_FRONTEND=noninteractive apt-get -yq -o DPkg::Lock::Timeout=300 upgrade",
                sudo=True,
            )
            logger.info("Done updating")

    def install_packages(self):
        with self.get_server_connection() as conn:
            exec_command(
                conn,
                "DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true",
                sudo=True,
            )
            self._apt_wait(conn)
            # Install common utilities in a single transaction to reduce lock contention
            exec_command(
                conn,
                "DEBIAN_FRONTEND=noninteractive apt-get -yq -o DPkg::Lock::Timeout=300 install mc git zsh host curl",
                sudo=True,
            )

    def get_server_info(self, no_cache: bool = False) -> Dict[str, str | int | float]:
        if not no_cache:
            if self._specs:
                return self._specs
            else:
                return {
                    "host": "Unknown",
                    "cpu_count": 0,
                    "ram_gb": 0,
                    "storage_gb": 0,
                    "pretty_name": "Unknown",
                }

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
            if host_info[-1] == ".":
                host_info = host_info[:-1].split(" ")[-1]
            else:
                # if host info returns an ip address there is no punctuation in the end
                host_info = host_info.split(" ")[-1]
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

        self._specs = info
        return info

    def add_mlox_user(self) -> None:
        mlox_user = self.get_mlox_user_template()
        # 1. add mlox user
        with self.get_server_connection() as conn:
            logger.info(
                f"Add user: {mlox_user.name}. Create home dir and add to sudo group."
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
            logger.info(f"Create .ssh dir for user {self.mlox_user.name}.")
            command = "mkdir -p ~/.ssh; chmod 700 ~/.ssh"
            exec_command(conn, command)

            # 2. generate rsa keys for remote user
            logger.info(f"Generate RSA keys for remote user on server {self.ip}.")
            command = f"cd {self.mlox_user.home}/.ssh; rm id_rsa*; ssh-keygen -b 4096 -t rsa -f id_rsa -N {remote_user.ssh_passphrase}"
            exec_command(conn, command, sudo=False)

            # 3. read pub and private keys and store to remote user
            remote_user.ssh_pub_key = fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa.pub", format="string"
            ).strip()
            remote_user.ssh_key = fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa", format="string"
            ).strip()

            # 4. generate rsa keys for mlox user
            logger.info(
                f"Generate RSA keys for {self.mlox_user.name} on server {self.ip}."
            )
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
            logger.error("Uh oh, something went while setting up the SSH connection.")
        else:
            logger.info(f"User {self.mlox_user.name} created.")

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
            # Instead: Use kill -HUP to reload sshd config. It's portable and works in containers without systemd.
            # exec_command(conn, "kill -HUP $(pidof sshd)", sudo=True)

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
            # Instead: Use kill -HUP to reload sshd config. It's portable and works in containers without systemd.
            # exec_command(conn, "kill -HUP $(pidof sshd)", sudo=True)

    # GIT
    def git_clone(self, repo_url: str, abs_path: str) -> None:
        with self.get_server_connection() as conn:
            fs_create_dir(conn, abs_path)
            exec_command(conn, f"cd {abs_path}; yes | git clone {repo_url}", sudo=False)

    def git_pull(self, abs_path: str) -> None:
        # TODO check if the path exists, rn we assume the path is valid
        with self.get_server_connection() as conn:
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
        if self.state != "running":
            status_info["backend.is_running"] = False
        else:
            status_info["backend.is_running"] = True
        return status_info

    def start_backend_runtime(self) -> None:
        logger.info("Native backend start.")

    def stop_backend_runtime(self) -> None:
        logger.info("Native backend stop.")
