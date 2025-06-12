import os
from mlox.infra import Infrastructure
from mlox.server import AbstractServer
from mlox.remote import exec_command

if __name__ == "__main__":
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    else:
        server = Infrastructure.load("/mlox.key", password)

        # print(f"Loaded server config: {bundle}")
        # infra.save("infrastructure.json", password)
        # print("\n")
        # loaded_infra = Infrastructure.load("/infrastructure.json", password)
        print(f"Loaded server: {server}")

        with server.get_server_connection() as conn:
            print("Connection established successfully.")
            user = "admin"
            pw = "admin123"
            hashed_pw = exec_command(
                conn,
                # f"echo $(htpasswd -nb {user} {pw}) | sed -e s/\\$/\\$\\$/g",
                f"htpasswd",
                sudo=True,
                pty=True,
            )

            print(f"Hashed password for {user}: {hashed_pw.strip()}")
