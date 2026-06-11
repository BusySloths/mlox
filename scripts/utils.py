import os
import logging

from mlox.infra import Infrastructure
from mlox.session import MloxSession

logger = logging.getLogger(__name__)


def load_mlox_infra() -> Infrastructure:
    mlox_path = os.environ.get("MLOX_PROJECT_PATH", None)
    mlox_password = os.environ.get("MLOX_PROJECT_PASSWORD", None)
    # Make sure your environment variable is set!
    if not mlox_password or not mlox_path:
        print(
            "Error: MLOX_PROJECT_PASSWORD or MLOX_PROJECT_PATH environment variable is not set."
        )
        exit(1)
    session = MloxSession(mlox_path, mlox_password)
    return session.infra
