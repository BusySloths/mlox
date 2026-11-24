import logging
from ipaddress import ip_address

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import shlex
from typing import Dict, Any, ClassVar

from mlox.executors import TaskGroup
from mlox.firewall import FirewallPolicy, FirewallPolicyRule, FirewallStatus
from mlox.execution.firewall_policy import validate_ssh_policy
from mlox.contracts.servers import AbstractTunnelServer
from mlox.servers.ubuntu.firewall import parse_firewall_status
from mlox.servers.ubuntu.firewall_grants import observed_ssh_client, parse_grant_listing, render_grant_mutation, render_list_grants
from mlox.firewall_grants import FirewallAccessGrant
from mlox.servers.ubuntu.tunnel import open_ssh_tunnel
from mlox.server import (
    AbstractFirewallServer,
    AbstractGitServer,
    AbstractInitialPasswordAuthServer,
    AbstractLogServer,
    AbstractNativeServer,
    AbstractServer,
    ServerCapability,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class UbuntuNativeServer(
    AbstractServer,
    AbstractGitServer,
    AbstractFirewallServer,
    AbstractInitialPasswordAuthServer,
    AbstractNativeServer,
    AbstractLogServer,
    AbstractTunnelServer,
):
    capabilities: ClassVar[set[ServerCapability]] = {
        ServerCapability.GIT,
        ServerCapability.FIREWALL,
        ServerCapability.TUNNEL,
        ServerCapability.INITIAL_AUTH_PASSWORD,
        ServerCapability.TERMINAL,
        ServerCapability.NATIVE,
        ServerCapability.LOGS,
    }

    DEFAULT_SERVER_INFO: ClassVar[Dict[str, str | int | float]] = {
        "host": "Unknown",
        "cpu_count": 0,
        "ram_gb": 0,
        "storage_gb": 0,
        "pretty_name": "Unknown",
    }
    _specs: Dict[str, str | int | float] | None = field(default=None, init=False)
    is_debug_access_enabled: bool = field(default=False, init=False)

    def __post_init__(self):
        super().__post_init__()
        self.backend = ["native"]

    def open_tunnel(self, endpoint):
        return open_ssh_tunnel(self, endpoint)

    def log_labels(self) -> list[str]:
        return ["System journal"]

    def log_tail(self, conn, label: str | None = None, tail: int = 200) -> str:
        if label not in (None, "System journal"):
            raise ValueError(f"Unknown server log source: {label}")
        if not isinstance(tail, int) or isinstance(tail, bool) or tail < 1:
            raise ValueError("Log tail must be a positive integer.")
        result = conn.sudo(
            f"journalctl --no-pager --output=short-iso -n {tail}",
            hide=True, warn=True, pty=False, in_stream=False, timeout=30,
        )
        if result.exited:
            detail = result.stderr.removeprefix("[sudo] password: ").strip()
            raise RuntimeError(
                f"Journal retrieval failed (exit {result.exited}): {detail}"
            )
        return result.stdout.rstrip("\n")

    def _apt_wait(self, conn) -> None:
        """Wait until apt/dpkg locks are free to avoid contention errors."""
        try:
            self.exec.sys_apt_wait(conn)
        except Exception as e:
            logger.warning(f"apt-wait encountered an issue (continuing): {e}")

    def setup(self):
        if self.state != "un-initialized":
            logging.error("Can not initialize an already initialized server.")
            return
        self.state = "starting"
        try:
            self.update()
            self.install_packages()
            self.update()
            self.add_mlox_user()
            self.setup_users()
            self.setup_backend()
            self.disable_password_authentication()
            self.state = "running"
        except Exception:
            self.state = "un-initialized"
            raise

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
            self.exec.sys_update_system_packages(conn)
            logger.info("Done updating")

    def install_packages(self):
        with self.get_server_connection() as conn:
            self.exec.execute(
                conn,
                "DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true",
                group=TaskGroup.SYSTEM_PACKAGES,
                sudo=True,
            )
            self._apt_wait(conn)
            # Update package list before installing to avoid "package not found" errors
            self.exec.execute(
                conn,
                (
                    "DEBIAN_FRONTEND=noninteractive apt-get -yq "
                    "-o DPkg::Lock::Timeout=300 update"
                ),
                group=TaskGroup.SYSTEM_PACKAGES,
                sudo=True,
            )
            # Install common utilities in a single transaction to reduce lock contention
            self.exec.execute(
                conn,
                (
                    "DEBIAN_FRONTEND=noninteractive apt-get -yq "
                    "-o DPkg::Lock::Timeout=300 install "
                    "mc git zsh host curl openssl iptables ipset || true"
                ),
                group=TaskGroup.SYSTEM_PACKAGES,
                sudo=True,
            )
            installed = self.exec.execute(
                conn,
                "sh -c 'command -v ipset >/dev/null && echo MLOX_IPSET_READY'",
                group=TaskGroup.SYSTEM_PACKAGES,
                sudo=True,
            )
            if not installed or "MLOX_IPSET_READY" not in installed:
                raise RuntimeError("Server setup could not install ipset, which is required for temporary firewall access.")

    def get_server_info(self, no_cache: bool = False) -> Dict[str, str | int | float]:
        if not no_cache:
            if self._specs:
                return self._specs
            else:
                return self.DEFAULT_SERVER_INFO.copy()

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
            hardware_info = self.exec.execute(
                conn,
                cmd,
                group=TaskGroup.NETWORKING,
                sudo=True,
            )
            system_info = self.exec.sys_get_distro_info(conn)
            host_info = self.exec.execute(
                conn,
                f"host {conn.host}",
                group=TaskGroup.NETWORKING,
                sudo=False,
            )

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
            self.exec.sys_add_user(
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
            self.exec.fs_create_dir(conn, "~/.ssh")
            self.exec.fs_set_permissions(conn, "~/.ssh", "700")

            # 2. generate rsa keys for remote user
            logger.info(f"Generate RSA keys for remote user on server {self.ip}.")
            command = (
                f"cd {self.mlox_user.home}/.ssh; rm id_rsa*; "
                f"ssh-keygen -b 4096 -t rsa -f id_rsa -N {remote_user.ssh_passphrase}"
            )
            self.exec.execute(
                conn,
                command,
                group=TaskGroup.SECURITY_ASSETS,
            )

            # 3. read pub and private keys and store to remote user
            remote_user.ssh_pub_key = self.exec.fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa.pub", format="string"
            ).strip()
            remote_user.ssh_key = self.exec.fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa", format="string"
            ).rstrip("\r\n") + "\n"

            # 4. generate rsa keys for mlox user
            logger.info(
                f"Generate RSA keys for {self.mlox_user.name} on server {self.ip}."
            )
            command = (
                f"cd {self.mlox_user.home}/.ssh; rm id_rsa*; "
                f"ssh-keygen -b 4096 -t rsa -f id_rsa -N {self.mlox_user.ssh_passphrase}"
            )
            self.exec.execute(
                conn,
                command,
                group=TaskGroup.SECURITY_ASSETS,
            )

            # 5. read pub and private keys and store to mlox user
            self.mlox_user.ssh_pub_key = self.exec.fs_read_file(
                conn, f"{self.mlox_user.home}/.ssh/id_rsa.pub", format="string"
            ).strip()

            # 6. add remote user public key to authorized_keys
            self.exec.fs_append_line(
                conn,
                f"{self.mlox_user.home}/.ssh/authorized_keys",
                remote_user.ssh_pub_key,
            )

            # 7. get user system id
            self.mlox_user.uid = self.exec.sys_user_id(conn)

        self.remote_user = remote_user
        if not self.test_connection():
            logger.error("Uh oh, something went while setting up the SSH connection.")
        else:
            logger.info(f"User {self.mlox_user.name} created.")

    def disable_password_authentication(self):
        with self.get_server_connection() as conn:
            # 1. uncomment if comment out
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "#PasswordAuthentication",
                "PasswordAuthentication",
                sudo=True,
            )
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "#PubkeyAuthentication",
                "PubkeyAuthentication",
                sudo=True,
            )

            # 2. Disable includes
            self.exec.fs_find_and_replace(
                conn, "/etc/ssh/sshd_config", "Include", "#Include", sudo=True
            )

            # 2. change to desired value
            self.exec.fs_find_and_replace(
                conn, "/etc/ssh/sshd_config", "UsePAM yes", "UsePAM no", sudo=True
            )
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "PasswordAuthentication yes",
                "PasswordAuthentication no",
                sudo=True,
            )
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "KeyboardInteractiveAuthentication yes",
                "KeyboardInteractiveAuthentication no",
                sudo=True,
            )
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "PubkeyAuthentication no",
                "PubkeyAuthentication yes",
                sudo=True,
            )
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "X11Forwarding yes",
                "X11Forwarding no",
                sudo=True,
            )
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "AllowTcpForwarding yes",
                "AllowTcpForwarding no",
                sudo=True,
            )
            # Any value, commented or not (Ubuntu ships "#PermitRootLogin prohibit-password"),
            # so root cannot log in at all, not even with a key.
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "^#\\?PermitRootLogin .*",
                "PermitRootLogin no",
                sudo=True,
            )
            self.exec.execute(
                conn,
                "systemctl restart ssh",
                group=TaskGroup.SERVICE_CONTROL,
                sudo=True,
            )
            self.exec.execute(
                conn,
                "systemctl reload ssh",
                group=TaskGroup.SERVICE_CONTROL,
                sudo=True,
            )
            # Instead: Use kill -HUP to reload sshd config. It's portable and works in containers without systemd.
            # self.exec.exec_command(conn, "kill -HUP $(pidof sshd)", sudo=True)

    def enable_password_authentication(self):
        with self.get_server_connection() as conn:
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "#PasswordAuthentication",
                "PasswordAuthentication",
                sudo=True,
            )
            self.exec.fs_find_and_replace(
                conn,
                "/etc/ssh/sshd_config",
                "PasswordAuthentication no",
                "PasswordAuthentication yes",
                sudo=True,
            )
            self.exec.execute(
                conn,
                "systemctl restart ssh",
                group=TaskGroup.SERVICE_CONTROL,
                sudo=True,
            )
            self.exec.execute(
                conn,
                "systemctl reload ssh",
                group=TaskGroup.SERVICE_CONTROL,
                sudo=True,
            )
            # Instead: Use kill -HUP to reload sshd config. It's portable and works in containers without systemd.
            # self.exec.exec_command(conn, "kill -HUP $(pidof sshd)", sudo=True)

    # GIT
    def git_clone(self, repo_url: str, abs_path: str) -> None:
        with self.get_server_connection() as conn:
            self.exec.fs_create_dir(conn, abs_path)
            self.exec.execute(
                conn,
                f"cd {abs_path}; yes | git clone {repo_url}",
                group=TaskGroup.VERSION_CONTROL,
                sudo=False,
            )

    def git_pull(self, abs_path: str) -> None:
        # TODO check if the path exists, rn we assume the path is valid
        with self.get_server_connection() as conn:
            self.exec.execute(
                conn,
                f"cd {abs_path}; git pull",
                group=TaskGroup.VERSION_CONTROL,
                sudo=False,
            )

    def git_remove(self, abs_path: str) -> None:
        with self.get_server_connection() as conn:
            self.exec.fs_delete_dir(conn, abs_path)

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

    def firewall_peer_address(self) -> str | None:
        try:
            address = ip_address(self.ip)
        except ValueError:
            return None
        return str(address) if address.is_global else None

    def firewall_default_policy(self) -> FirewallPolicy:
        return FirewallPolicy((int(self.port), 80, 443))

    def firewall_validate_policy(self, policy: FirewallPolicy) -> None:
        validate_ssh_policy(policy, int(self.port))

    def firewall_policy_rules(self) -> tuple[FirewallPolicyRule, ...]:
        return (
            FirewallPolicyRule("Existing connections", "Already tracked: established / related", "Allow"),
            FirewallPolicyRule("IPv6 control", "ICMPv6", "Allow"),
            FirewallPolicyRule("Container bridges", "Standard Docker bridges", "Host + Docker"),
            FirewallPolicyRule("Other inbound", "All other traffic", "Block"),
        )

    def firewall_apply_policy(self, policy: FirewallPolicy) -> None:
        self.firewall_validate_policy(policy)
        with self.get_server_connection() as conn:
            self.exec.firewall_apply_policy(conn, policy, int(self.port), docker=False)

    def _firewall_grant_profile(self) -> tuple[bool, bool]:
        return False, False

    def _run_grant_script(self, conn, script: str) -> str:
        # Keep the executor's normal audit trail while returning the remote
        # command's stderr to the caller, including for a nonzero exit status.
        wrapped = (f"if output=$(sh -c {shlex.quote(script)} 2>&1); then "
                   "printf '%s\\n' \"$output\"; else code=$?; "
                   "printf 'MLOX_GRANT_ERROR %s\\n%s\\n' \"$code\" \"$output\"; fi")
        result = self.exec.execute(conn, f"sh -c {shlex.quote(wrapped)}", group=TaskGroup.NETWORKING, sudo=True)
        if result is None:
            raise RuntimeError("Could not execute the temporary firewall operation over sudo. Check the SSH connection and sudo credentials.")
        if result.startswith("MLOX_GRANT_ERROR "):
            header, _, detail = result.partition("\n")
            raise RuntimeError(f"Temporary firewall operation failed ({header.removeprefix('MLOX_GRANT_ERROR ')}): {detail.strip() or 'the remote command returned no error output.'}")
        return result

    def firewall_grant_current_client(self, grant_id: str, duration_seconds: int) -> FirewallAccessGrant | None:
        with self.get_server_connection() as conn:
            status = parse_firewall_status(self.exec.firewall_status(conn))
            if status.active is False:
                return None
            if status.active is not True or status.error:
                raise RuntimeError(status.error or "Firewall status is unknown.")
            address = observed_ssh_client(conn)
            docker, k3s = self._firewall_grant_profile()
            output = self._run_grant_script(conn, render_grant_mutation(grant_id, address=address, duration_seconds=duration_seconds, docker=docker, k3s=k3s))
            line = next((line for line in output.splitlines() if line.startswith("MLOX_GRANT ")), None)
            if line is None:
                raise RuntimeError("Temporary firewall grant was not confirmed.")
            _, ident, actual_address, expiry = line.split()
            return FirewallAccessGrant(ident, actual_address, datetime.fromtimestamp(int(expiry), timezone.utc))

    def firewall_remove_client_grant(self, grant_id: str) -> None:
        docker, k3s = self._firewall_grant_profile()
        with self.get_server_connection() as conn:
            output = self._run_grant_script(conn, render_grant_mutation(grant_id, address=None, duration_seconds=None, docker=docker, k3s=k3s))
            if "MLOX_GRANT_REMOVED" not in output.splitlines():
                raise RuntimeError("Temporary firewall grant removal was not confirmed.")

    def firewall_list_client_grants(self) -> tuple[FirewallAccessGrant, ...]:
        with self.get_server_connection() as conn:
            return parse_grant_listing(self._run_grant_script(conn, render_list_grants()))

    def firewall_persist_policy(self, policy: FirewallPolicy) -> None:
        self.firewall_validate_policy(policy)
        with self.get_server_connection() as conn:
            self.exec.firewall_persist_policy(conn, policy, int(self.port), docker=False)

    def firewall_down(self) -> None:
        with self.get_server_connection() as conn:
            self.exec.firewall_down(conn)

    def firewall_status(self) -> FirewallStatus:
        with self.get_server_connection() as conn:
            status = parse_firewall_status(self.exec.firewall_status(conn))
            if status.active is True:
                try:
                    status = replace(status, temporary_grants=parse_grant_listing(self._run_grant_script(conn, render_list_grants())))
                except Exception:
                    pass  # Preserve the firewall status; the grant list remains unknown.
            return status
