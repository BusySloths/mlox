from mlox.secret_manager import load_secret_manager_from_keyfile


def list_secrets(fname: str, pw: str) -> None:
    sm = load_secret_manager_from_keyfile(fname, pw)
    if not sm:
        print("No secret manager could be loaded from the provided file.")
        return
    print(sm.list_secrets())


if __name__ == "__main__":
    list_secrets("/my_demo_keyfile.key", "ROcxU3d6G%GsT3=!")
    print("Secrets listed.")
