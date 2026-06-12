"""List secret names embedded in the active encrypted MLOX project."""
from mlox.project import load_project_workspace


if __name__ == "__main__":
    workspace = load_project_workspace()
    for name in workspace.secrets.list_secrets(keys_only=True):
        print(name)
