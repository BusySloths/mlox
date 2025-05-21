import os

from mlox.server import AbstractServer
from mlox.service import AbstractService
from mlox.secret_manager import TinySecretManager
from mlox.utils import dict_to_dataclass
from mlox.remote import fs_find_and_replace, exec_command


def enable_password_authentication(bundle_name: str):
    # Make sure your environment variable is set!
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
        exit(1)

    secret_manager = TinySecretManager("/mlox.key", ".secrets", password)

    infra = None
    infra_dict = secret_manager.load_secret("MLOX_CONFIG_INFRASTRUCTURE")
    if infra_dict and isinstance(infra_dict, dict):
        infra = dict_to_dataclass(infra_dict, hooks=[AbstractServer, AbstractService])

    if not infra:
        print("Could not load infrastructure")
        return

    server = next((b.server for b in infra.bundles if b.name == bundle_name), None)

    if not server:
        print(f"Could not find bundle with name {bundle_name}")
        return

    with server.get_server_connection() as conn:
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
            "PasswordAuthentication no",
            "PasswordAuthentication yes",
            sudo=True,
        )
        # fs_find_and_replace(
        #     conn,
        #     "/etc/ssh/sshd_config",
        #     "KeyboardInteractiveAuthentication yes",
        #     "KeyboardInteractiveAuthentication no",
        #     sudo=True,
        # )
        # fs_find_and_replace(
        #     conn,
        #     "/etc/ssh/sshd_config",
        #     "PubkeyAuthentication no",
        #     "PubkeyAuthentication yes",
        #     sudo=True,
        # )
        exec_command(conn, "systemctl restart ssh", sudo=True)
        exec_command(conn, "systemctl reload ssh", sudo=True)

    print(f"IP: ", server.ip)
    print(f"USER: ", server.mlox_user.name)
    print(f"PASSWORD: ", server.mlox_user.pw)

    print(f"ssh {server.mlox_user.name}@{server.ip} -p {server.port}")


if __name__ == "__main__":
    enable_password_authentication("Primary")
