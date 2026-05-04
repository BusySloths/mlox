"""Compatibility wrapper for the lightweight MLflow Gateway app.

The gateway implementation lives in ``mlox.services.mlflow_gateway.serve``.
This module remains so older imports keep working.
"""

from mlox.services.mlflow_gateway.serve import *  # noqa: F401,F403
