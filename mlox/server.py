import time  # Added for retry delay
import logging
import tempfile
import importlib

from datetime import datetime
from dataclasses import dataclass, field
from abc import abstractmethod, ABC
from typing import Dict, Optional, List, Literal, Any

from fabric import Connection  # type: ignore
from paramiko.ssh_exception import (  # type: ignore
    SSHException,
    AuthenticationException,
    NoValidConnectionsError,
)
import socket

from mlox.utils import generate_password
from mlox.remote import open_connection, close_connection, exec_command, fs_read_file

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
class AbstractGitServer(ABC):
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


@dataclass
class AbstractServer(ABC):
    ip: str
    root: str
    root_pw: str
    service_config_id: str
    port: str = field(default="22")

    mlox_user: MloxUser | None = field(default=None, init=False)
    remote_user: RemoteUser | None = field(default=None, init=False)

    backend: List[str] = field(default_factory=list, init=False)
    state: Literal[
        "un-initialized", "no-backend", "starting", "running", "shutdown", "unknown"
    ] = "un-initialized"
    discovered: str | None = field(default=None, init=False)

    def __post_init__(self):
        if not self.discovered:
            self.discovered = datetime.now().isoformat()

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
                if conn.is_connected:
                    verified = True
            print(f"Public key SSH login verified={verified}.")
        except Exception as e:
            print(f"Failed to login via SSH with public key: {e}")
        return verified

    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def update(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def get_server_info(self, no_cache: bool = False) -> Dict[str, str | int | float]:
        pass

    @abstractmethod
    def enable_debug_access(self) -> None:
        pass

    @abstractmethod
    def disable_debug_access(self) -> None:
        pass

    # Backend
    @abstractmethod
    def setup_backend(self) -> None:
        pass

    @abstractmethod
    def teardown_backend(self) -> None:
        pass

    @abstractmethod
    def get_backend_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def start_backend_runtime(self) -> None:
        pass

    @abstractmethod
    def stop_backend_runtime(self) -> None:
        pass


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
