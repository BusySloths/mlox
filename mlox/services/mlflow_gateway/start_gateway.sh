#!/usr/bin/env bash
set -e

echo "--- mlox MLflow Gateway Startup ---"
echo "MLFLOW_TRACKING_URI: ${MLFLOW_TRACKING_URI}"

if [ -s /app/gateway-requirements.txt ]; then
    echo "Installing gateway requirements from /app/gateway-requirements.txt"
    pip install --no-cache-dir -r /app/gateway-requirements.txt
else
    echo "No additional gateway requirements configured."
fi

exec uvicorn serve:app --host 0.0.0.0 --port 8080
