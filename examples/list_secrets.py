"""List secret names embedded in the active encrypted MLOX project."""
from mlox.session import load_mlox_session


if __name__ == "__main__":
    session = load_mlox_session()
    for name in session.secrets.list_secrets(keys_only=True):
        print(name)
