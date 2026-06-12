import os

from mlox.project import ProjectWorkspace


def load_project_workspace() -> ProjectWorkspace:
    mlox_path = os.environ.get("MLOX_PROJECT_PATH", None)
    mlox_password = os.environ.get("MLOX_PROJECT_PASSWORD", None)
    # Make sure your environment variable is set!
    if not mlox_password or not mlox_path:
        print(
            "Error: MLOX_PROJECT_PASSWORD or MLOX_PROJECT_PATH environment variable is not set."
        )
        exit(1)
    return ProjectWorkspace.open(mlox_path, mlox_password)


if __name__ == "__main__":
    print("Loading MLOX project...")
    print(
        "Make sure MLOX_PROJECT_PATH and MLOX_PROJECT_PASSWORD environment variables are set and a project exists."
    )
    workspace = load_project_workspace()
    print("Project loaded:", workspace.name)
