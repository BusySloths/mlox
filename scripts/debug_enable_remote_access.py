import os
import os

from mlox.session import MloxSession


def enable_password_authentication(bundle_name: str):
    # Make sure your environment variable is set!
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
        exit(1)

    project = (
        os.environ.get("MLOX_CONFIG_USER")
        or os.environ.get("MLOX_PROJECT")
        or "mlox"
    )

    session = MloxSession(project, password)
    if not session.secrets or not session.secrets.is_working():
        print("Project does not have an active secret manager configured.")
        return

    infra = session.infra
    if not infra or not infra.bundles:
        print("Could not load infrastructure")
        return

    server = next((b.server for b in infra.bundles if b.name == bundle_name), None)

    if not server:
        print(f"Could not find bundle with name {bundle_name}")
        return

    executor = server.exec
    with server.get_server_connection() as conn:
        # 1. uncomment if comment out
        executor.fs_find_and_replace(
            conn,
            "/etc/ssh/sshd_config",
            "#PasswordAuthentication",
            "PasswordAuthentication",
            sudo=True,
        )
        executor.fs_find_and_replace(
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
        executor.exec_command(conn, "systemctl restart ssh", sudo=True)
        executor.exec_command(conn, "systemctl reload ssh", sudo=True)

    print(f"IP: ", server.ip)
    print(f"USER: ", server.mlox_user.name)
    print(f"PASSWORD: ", server.mlox_user.pw)

    print(f"ssh {server.mlox_user.name}@{server.ip} -p {server.port}")


if __name__ == "__main__":
    enable_password_authentication("Primary")
