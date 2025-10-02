import os
from mlox.session import MloxSession
from mlox.secret_manager import TinySecretManager
from mlox.infra import Infrastructure, Bundle
from mlox.utils import dataclass_to_dict

if __name__ == "__main__":
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    else:
        session = MloxSession("mlox", password)

        # print(session.infra)

        # session.save_infrastructure()
        # server = Infrastructure.load("/mlox333.key", password)
        # infra = Infrastructure()
        # infra.bundles.append(Bundle(name="test", server=server))

        # tsm = TinySecretManager("/mlox333.key", ".secrets", password)
        # print(tsm.list_secrets())
        # tsm.save_secret("INFRA", dataclass_to_dict(server))

        # print(f"Loaded server config: {bundle}")
        # infra.save("infrastructure.json", password)
        # print("\n")
        # loaded_infra = Infrastructure.load("/infrastructure.json", password)
        # print(f"Loaded server: {server}")

        # with server.get_server_connection() as conn:
        #     print("Connection established successfully.")
        #     user = "admin"
        #     pw = "admin123"
        #     hashed_pw = exec_command(
        #         conn,
        #         # f"echo $(htpasswd -nb {user} {pw}) | sed -e s/\\$/\\$\\$/g",
        #         f"htpasswd",
        #         sudo=True,
        #         pty=True,
        #     )

        #     print(f"Hashed password for {user}: {hashed_pw.strip()}")
