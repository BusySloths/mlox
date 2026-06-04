from mlox.secret_manager import (
    load_secret_manager_from_keyfile,
    load_secret_manager_from_env,
)


def list_secrets(fname: str, pw: str, load_from_file: bool = True) -> None:
    if load_from_file:
        sm = load_secret_manager_from_keyfile(fname, pw)
    else:
        sm = load_secret_manager_from_env(fname, pw)
    if not sm:
        print("No secret manager could be loaded from the provided file.")
        return
    print(sm.list_secrets())


if __name__ == "__main__":
    # list_secrets("/my_demo_keyfile.key", "ROcxU3d6G%GsT3=!", load_from_file=True)
    print("--")
    list_secrets("MLOX_SECRET_MANAGER", "MLOX_SECRET_MANAGER_PW", load_from_file=False)
    print("Secrets listed.")
