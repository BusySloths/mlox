#!/bin/bash
# Startup script for MLflow + MLServer serving.
#
# Design:
#   1. Download model artifacts using the bootstrap Python (has mlflow pre-installed).
#   2. Read the required Python version from the model's python_env.yaml.
#   3. Install that Python via pyenv if not already present.
#   4. Switch to it (PYENV_VERSION), then install mlflow + mlserver + model deps there.
#   5. Exec mlflow models serve with --env-manager=local so MLServer runs in that Python.
#
# Why --env-manager=local:
#   mlflow models serve --enable-mlserver launches MLServer in the *current* Python process,
#   not inside a virtualenv. With --env-manager=local, all deps live in the active Python
#   (set via PYENV_VERSION), which is exactly where MLServer's worker processes look.
set -e

echo "--- MLflow Model Server Startup ---"
echo "MLFLOW_TRACKING_URI: ${MLFLOW_TRACKING_URI}"
echo "MLFLOW_REMOTE_MODEL: ${MLFLOW_REMOTE_MODEL}"

# --- Step 1: Download model artifacts ---
# Uses the bootstrap Python (pyenv global), which has mlflow pre-installed.
echo "Downloading model artifacts from models:/${MLFLOW_REMOTE_MODEL} ..."
MODEL_LOCAL_PATH=$(python - <<'PYEOF'
import mlflow, os
uri = "models:/" + os.environ["MLFLOW_REMOTE_MODEL"]
path = mlflow.artifacts.download_artifacts(uri)
print(path)
PYEOF
)
echo "Model artifacts at: ${MODEL_LOCAL_PATH}"

# --- Step 2: Read Python version from model metadata ---
# Try python_env.yaml first (virtualenv format), fall back to MLmodel.
if [ -f "${MODEL_LOCAL_PATH}/python_env.yaml" ]; then
    PYTHON_VERSION=$(awk '/^python:/{print $2; exit}' "${MODEL_LOCAL_PATH}/python_env.yaml")
elif [ -f "${MODEL_LOCAL_PATH}/MLmodel" ]; then
    PYTHON_VERSION=$(awk '/^python_version:/{print $2; exit}' "${MODEL_LOCAL_PATH}/MLmodel")
fi

if [ -z "${PYTHON_VERSION}" ]; then
    echo "WARNING: Could not determine Python version from model artifacts. Using current Python."
    PYTHON_VERSION=$(python -c "import platform; print(platform.python_version())")
fi
echo "Model requires Python: ${PYTHON_VERSION}"

# --- Step 3: Install target Python via pyenv if not already present ---
if pyenv versions --bare | grep -qx "${PYTHON_VERSION}"; then
    echo "Python ${PYTHON_VERSION} already installed."
else
    echo "Installing Python ${PYTHON_VERSION} via pyenv (compiling from source) ..."
    pyenv install "${PYTHON_VERSION}"
    pyenv rehash
fi

# --- Step 4: Switch all subsequent commands to the target Python ---
export PYENV_VERSION="${PYTHON_VERSION}"
echo "Active Python: $(python --version)"

# --- Step 5: Install mlflow + mlserver into the target Python ---
# If target == bootstrap Python (3.12.5), pip sees them pre-installed and is a near no-op.
# If target is a different version, pip installs fresh.
echo "Installing mlflow and mlserver into Python ${PYTHON_VERSION} ..."
pip install --no-cache-dir \
    "mlflow==3.8.1" \
    "mlflow[extras]==3.8.1" \
    "mlserver~=1.7.1" \
    "mlserver-mlflow~=1.7.1" \
    "uvloop==0.21.0"

# --- Step 6: Install model-specific requirements ---
REQ_FILE="${MODEL_LOCAL_PATH}/requirements.txt"
if [ -f "${REQ_FILE}" ]; then
    echo "Installing model requirements from ${REQ_FILE} ..."
    pip install --no-cache-dir -r "${REQ_FILE}"
else
    echo "No requirements.txt found in model artifacts — skipping."
fi

# --- Step 7: Serve ---
# PYENV_VERSION is still set, so mlflow and mlserver both resolve to the target Python.
echo "Starting MLServer on port 5002 | Host: ${MLSERVER_URL}"
exec mlflow models serve \
    -m "models:/${MLFLOW_REMOTE_MODEL}" \
    -p 5002 \
    -h 0.0.0.0 \
    -w 1 \
    --enable-mlserver \
    --env-manager=local
