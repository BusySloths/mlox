"""Saved integration models must load outside the repository."""

from contextlib import nullcontext
import importlib
import subprocess
import sys

import cloudpickle
import pytest


@pytest.mark.parametrize("module", ["mlflow_gateway", "mlflow_mlserver"])
def test_identity_model_loads_without_tests_package(module, monkeypatch, tmp_path):
    source = importlib.import_module(f"tests.integration.test_service_{module}")
    monkeypatch.setattr(source.mlflow, "pyfunc", importlib.import_module("mlflow.pyfunc"))
    artifact = tmp_path / "model.pkl"

    class ModelCaptured(Exception):
        pass

    def capture_model(*args, python_model, **kwargs):
        artifact.write_bytes(cloudpickle.dumps(python_model))
        raise ModelCaptured

    for name in ("set_tracking_uri", "set_registry_uri", "set_experiment"):
        monkeypatch.setattr(source.mlflow, name, lambda *args: None)
    monkeypatch.setattr(source.mlflow, "start_run", lambda **kwargs: nullcontext())
    monkeypatch.setattr(source.mlflow.pyfunc, "log_model", capture_model)
    # The helper sets these during registration; restore them after the test.
    for name in ("MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD", "MLFLOW_TRACKING_INSECURE_TLS"):
        monkeypatch.setenv(name, "test")
    with pytest.raises(ModelCaptured):
        source._register_identity_model("https://example.invalid", "user", "pw")
    result = subprocess.run(
        [sys.executable, "-I", "-c",
         "import cloudpickle,sys,pandas as pd; "
         "model=cloudpickle.load(open(sys.argv[1], 'rb')); "
         "data=pd.DataFrame([[1.,2.]]); "
         "pd.testing.assert_frame_equal(model.predict(None,data),data)", str(artifact)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
