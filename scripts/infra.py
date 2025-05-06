import os
from mlox.infra import Infrastructure


if __name__ == "__main__":
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    else:
        infra = Infrastructure()
        bundle = infra.load_server_config("/test_server.json", password)

        # print(f"Loaded server config: {bundle}")

        infra.save("infrastructure.json", password)
        print("\n")
        loaded_infra = Infrastructure.load("/infrastructure.json", password)
        print(f"Loaded infrastructure: {loaded_infra}")
