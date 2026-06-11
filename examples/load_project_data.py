import os

from mlox.session import ProjectSession


def load_project_session() -> ProjectSession:
    mlox_path = os.environ.get("MLOX_PROJECT_PATH", None)
    mlox_password = os.environ.get("MLOX_PROJECT_PASSWORD", None)
    # Make sure your environment variable is set!
    if not mlox_password or not mlox_path:
        print(
            "Error: MLOX_PROJECT_PASSWORD or MLOX_PROJECT_PATH environment variable is not set."
        )
        exit(1)
    return ProjectSession.open(mlox_path, mlox_password)


if __name__ == "__main__":
    print("Loading MLOX project...")
    print(
        "Make sure MLOX_PROJECT_PATH and MLOX_PROJECT_PASSWORD environment variables are set and a project exists."
    )
    session = load_project_session()
    print("Project loaded:", session.project.name)
