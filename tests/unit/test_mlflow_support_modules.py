from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd

from mlox.services.mlflow import mlops, serve


class _Span:
    def set_inputs(self, *_args, **_kwargs):
        return None

    def set_attribute(self, *_args, **_kwargs):
        return None

    def set_outputs(self, *_args, **_kwargs):
        return None


@contextmanager
def _cm_span():
    yield _Span()


@contextmanager
def _cm_empty():
    yield object()


class _TrackedModel(mlops.DeployableModel):
    def tracked_training(self, params=None):
        return {"artifact": "value"}

    def live_predict(self, input, params=None, artifacts=None):
        return pd.DataFrame({"y": [1 for _ in range(len(input))]})


def test_mlops_service_tracks_models_and_predicts(monkeypatch, tmp_path):
    monkeypatch.setenv("MLFLOW_URI", "https://mlflow.local")
    model = _TrackedModel()
    svc = mlops.MLFlowDeployableModelService(
        model=model,
        model_class="DemoModel",
        code_paths=[str(tmp_path), "missing/dir"],
    )
    svc.set_registered_model_name("demo-registry")

    calls = {"set_tracking_uri": [], "set_registry_uri": [], "set_tag": []}

    monkeypatch.setattr(mlops.mlflow, "set_tracking_uri", lambda v: calls["set_tracking_uri"].append(v))
    monkeypatch.setattr(mlops.mlflow, "set_registry_uri", lambda v: calls["set_registry_uri"].append(v))
    monkeypatch.setattr(mlops.mlflow, "set_experiment", lambda *_: None)
    monkeypatch.setattr(mlops.mlflow, "start_run", lambda **_kwargs: _cm_empty())
    monkeypatch.setattr(mlops.mlflow, "start_span", lambda *_args, **_kwargs: _cm_span())
    monkeypatch.setattr(mlops.mlflow.models, "infer_signature", lambda *_args, **_kwargs: "sig")
    monkeypatch.setattr(mlops.mlflow, "set_tag", lambda k, v: calls["set_tag"].append((k, v)))

    logged = {}
    monkeypatch.setattr(
        mlops.mlflow.pyfunc,
        "log_model",
        lambda **kwargs: logged.update(kwargs),
    )

    sample = np.array([[1.0], [2.0]])
    svc.track_model(params={"x": 1}, input_example=sample, inference_params={"a": 1})
    assert calls["set_tracking_uri"] == ["https://mlflow.local"]
    assert calls["set_registry_uri"] == ["https://mlflow.local"]
    assert logged["artifact_path"] == "DemoModel"
    assert logged["registered_model_name"] == "demo-registry"

    ctx = SimpleNamespace(artifacts={"a": 1}, model_config={"b": 2})
    svc.load_context(ctx)
    assert svc.artifacts == {"a": 1}
    assert svc.model_config == {"b": 2}

    out = svc.predict(context=None, model_input=sample, params={"p": 1})
    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == ["y"]

    class _BrokenModel(_TrackedModel):
        def live_predict(self, input, params=None, artifacts=None):
            raise RuntimeError("boom")

    err_svc = mlops.MLFlowDeployableModelService(_BrokenModel(), "Broken")
    err_out = err_svc.predict(context=None, model_input=sample, params=None)
    assert "error" in err_out.columns

    env = svc.get_conda_env()
    assert env["name"] == "mlflow-models"
    req_svc = mlops.MLFlowDeployableModelService(
        model=model,
        model_class="ReqModel",
        requirements_file="requirements.txt",
    )
    req_env = req_svc.get_conda_env()
    assert "-r requirements.txt" in req_env["dependencies"][1]["pip"][0]


def test_mlops_list_versions_for_model(monkeypatch):
    monkeypatch.setenv("MLFLOW_URI", "https://mlflow.local")

    class _Client:
        def search_model_versions(self, filter_string):
            return [SimpleNamespace(version="1"), SimpleNamespace(version="2")]

    monkeypatch.setattr(mlops, "MlflowClient", _Client)
    monkeypatch.setattr(mlops.mlflow, "set_tracking_uri", lambda *_: None)
    monkeypatch.setattr(mlops.mlflow, "set_registry_uri", lambda *_: None)
    rows = mlops.list_versions_for_model("Demo")
    assert len(rows) == 2


def test_serve_run_predict_and_list_models(monkeypatch):
    serve.model_cache.clear()

    class _LoadedModel:
        def predict(self, input_data, params=None):
            return pd.DataFrame({"result": [float(np.sum(input_data))]})

    monkeypatch.setattr(serve.mlflow.pyfunc, "load_model", lambda model_uri: _LoadedModel())

    req = serve.PredictionRequest(
        input_data=[[1.0, 2.0]],
        params={"a": True},
        registry_model_name="Demo",
        registry_model_version=1,
    )
    parsed, cached = serve.runandget(req)
    assert cached is False
    assert parsed[0]["result"] == 3.0

    parsed2, cached2 = serve.runandget(req)
    assert cached2 is True
    assert parsed2[0]["result"] == 3.0

    response = serve.predict(req)
    assert response["is_cached_model"] is True
    assert response["prediction_time_sec"] >= 0

    class _Version:
        def __init__(self, version):
            self.version = version
            self.creation_timestamp = 1730000000000
            self.run_id = f"run-{version}"
            self.tags = {}
            self.description = ""

    class _Client:
        def search_model_versions(self, filter_string):
            return [_Version("1"), _Version("2")]

    monkeypatch.setattr(serve.mlflow, "MlflowClient", _Client)
    models = serve.list_models("Demo")
    assert models["model"] == "Demo"
    assert len(models["versions"]) == 2


def test_serve_predict_error_mapping(monkeypatch):
    class _RestException(Exception):
        pass

    monkeypatch.setattr(serve.mlflow.exceptions, "RestException", _RestException)

    req = serve.PredictionRequest(
        input_data=[[1.0]],
        params=None,
        registry_model_name="Demo",
        registry_model_version=1,
    )

    monkeypatch.setattr(serve, "runandget", lambda _req: (_ for _ in ()).throw(_RestException("missing")))
    try:
        serve.predict(req)
        assert False, "Expected HTTPException for missing model"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404

    monkeypatch.setattr(serve, "runandget", lambda _req: (_ for _ in ()).throw(ValueError("bad input")))
    try:
        serve.predict(req)
        assert False, "Expected HTTPException for invalid input"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400

    monkeypatch.setattr(serve, "runandget", lambda _req: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        serve.predict(req)
        assert False, "Expected HTTPException for internal error"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 500


def test_serve_health_endpoint():
    serve.model_cache.clear()
    res = serve.health()
    assert isinstance(res["timestamp"], str)
    datetime.fromisoformat(res["timestamp"])
    assert res["cached_models_count"] == 0
