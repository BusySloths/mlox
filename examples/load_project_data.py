import os

from mlox.session import MloxSession


def load_mlox_session() -> MloxSession:
    mlox_name = os.environ.get("MLOX_PROJECT_NAME", None)
    mlox_password = os.environ.get("MLOX_PROJECT_PASSWORD", None)
    # Make sure your environment variable is set!
    if not mlox_password or not mlox_name:
        print(
            "Error: MLOX_PROJECT_PASSWORD or MLOX_PROJECT_NAME environment variable is not set."
        )
        exit(1)
    return MloxSession(mlox_name, mlox_password)


if __name__ == "__main__":
    print("Loading MLOX project...")
    print(
        "Make sure MLOX_PROJECT_NAME and MLOX_PROJECT_PASSWORD environment variables are set and a project exists."
    )
    session = load_mlox_session()
    print("Project loaded:", session.project.name)
