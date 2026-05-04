from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from mlox.services.mlflow import mlops
from mlox.services.mlflow_gateway import serve


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
    model_info = SimpleNamespace(
        run_id="run-123",
        registered_model_version=7,
        model_uri="runs:/run-123/DemoModel",
    )
    monkeypatch.setattr(
        mlops.mlflow.pyfunc,
        "log_model",
        lambda **kwargs: logged.update(kwargs) or model_info,
    )

    sample = np.array([[1.0], [2.0]])
    returned_model_info = svc.track_model(
        params={"x": 1}, input_example=sample, inference_params={"a": 1}
    )
    assert calls["set_tracking_uri"] == ["https://mlflow.local"]
    assert calls["set_registry_uri"] == ["https://mlflow.local"]
    assert logged["name"] == "DemoModel"
    assert logged["registered_model_name"] == "demo-registry"
    assert returned_model_info is model_info
    assert svc.logged_model_info is model_info
    assert svc.run_id == "run-123"
    assert svc.registered_model_version == 7

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


def test_mlops_code_paths_resolve_relative_to_cwd(monkeypatch, tmp_path):
    monkeypatch.setenv("MLFLOW_URI", "https://mlflow.local")
    project_dir = tmp_path / "project"
    code_dir = project_dir / "airml"
    code_dir.mkdir(parents=True)
    monkeypatch.chdir(project_dir)

    svc = mlops.MLFlowDeployableModelService(
        model=_TrackedModel(),
        model_class="DemoModel",
        code_paths=["./airml"],
    )

    resolved = svc._resolve_code_paths_for_logging()
    assert resolved == [str(code_dir.resolve())]


def test_mlops_default_code_paths_do_not_package_mlox_sources(monkeypatch):
    monkeypatch.setenv("MLFLOW_URI", "https://mlflow.local")
    svc = mlops.MLFlowDeployableModelService(
        model=_TrackedModel(),
        model_class="DemoModel",
    )

    resolved = svc._resolve_code_paths_for_logging()
    assert resolved == []

    with svc._prepared_code_paths_for_logging() as prepared:
        assert prepared == []


def test_mlops_prepared_code_paths_exclude_cache_directories(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("MLFLOW_URI", "https://mlflow.local")
    project_dir = tmp_path / "project"
    code_dir = project_dir / "airml"
    code_dir.mkdir(parents=True)
    monkeypatch.chdir(project_dir)

    (code_dir / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    (code_dir / ".mypy_cache").mkdir()
    (code_dir / ".mypy_cache" / "cache.json").write_text("{}", encoding="utf-8")
    (code_dir / "__pycache__").mkdir()
    (code_dir / "__pycache__" / "model.cpython-311.pyc").write_bytes(b"pyc")
    (code_dir / ".pytest_cache").mkdir()
    (code_dir / ".ruff_cache").mkdir()
    (code_dir / ".git").mkdir()
    (code_dir / ".venv").mkdir()
    (code_dir / "venv").mkdir()
    (code_dir / "pkg").mkdir()
    (code_dir / "pkg" / "__pycache__").mkdir()
    (code_dir / "pkg" / "__pycache__" / "nested.pyc").write_bytes(b"pyc")
    (code_dir / "pkg" / "live.py").write_text("print('ok')\n", encoding="utf-8")

    svc = mlops.MLFlowDeployableModelService(
        model=_TrackedModel(),
        model_class="DemoModel",
        code_paths=["./airml"],
    )

    with svc._prepared_code_paths_for_logging() as prepared:
        assert len(prepared) == 1
        staged_dir = Path(prepared[0])
        assert (staged_dir / "model.py").exists()
        assert (staged_dir / "pkg" / "live.py").exists()
        assert not (staged_dir / ".mypy_cache").exists()
        assert not (staged_dir / "__pycache__").exists()
        assert not (staged_dir / ".pytest_cache").exists()
        assert not (staged_dir / ".ruff_cache").exists()
        assert not (staged_dir / ".git").exists()
        assert not (staged_dir / ".venv").exists()
        assert not (staged_dir / "venv").exists()
        assert not (staged_dir / "pkg" / "__pycache__").exists()


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
    monkeypatch.setattr(
        serve.mlflow.artifacts,
        "download_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")),
    )

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
    cache = serve.list_cached_models()["cached_models"]
    assert cache[0]["model_uri"] == "models:/Demo/1"
    assert serve.clear_cached_models()["cleared_models_count"] == 1
    assert serve.model_cache == {}

    response = serve.predict(req)
    assert response["is_cached_model"] is False
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


def test_serve_model_uri_supports_version_or_alias():
    version_req = serve.PredictionRequest(
        input_data=[[1.0]],
        registry_model_name="Demo",
        registry_model_version=1,
    )
    alias_req = serve.PredictionRequest(
        input_data=[[1.0]],
        registry_model_name="Demo",
        registry_model_alias="champion",
    )

    assert serve._model_uri(version_req) == "models:/Demo/1"
    assert serve._model_uri(alias_req) == "models:/Demo@champion"

    with pytest.raises(ValueError):
        serve.PredictionRequest(
            input_data=[[1.0]],
            registry_model_name="Demo",
        )
    with pytest.raises(ValueError):
        serve.PredictionRequest(
            input_data=[[1.0]],
            registry_model_name="Demo",
            registry_model_version=1,
            registry_model_alias="champion",
        )


def test_serve_cache_evicts_by_ttl_and_lru(monkeypatch):
    serve.model_cache.clear()
    monkeypatch.setenv("MLOX_GATEWAY_CACHE_MAX_MODELS", "2")
    monkeypatch.setenv("MLOX_GATEWAY_CACHE_TTL_DAYS", "10")

    now = datetime(2026, 5, 4, 12, 0, 0)
    serve.model_cache["models:/Demo/old"] = serve.ModelCacheEntry(
        model=object(),
        sys_path=[],
        model_uri="models:/Demo/old",
        last_call=now - pd.Timedelta(days=11),
    )
    serve.model_cache["models:/Demo/1"] = serve.ModelCacheEntry(
        model=object(),
        sys_path=[],
        model_uri="models:/Demo/1",
        last_call=now - pd.Timedelta(days=2),
    )
    serve.model_cache["models:/Demo@champion"] = serve.ModelCacheEntry(
        model=object(),
        sys_path=[],
        model_uri="models:/Demo@champion",
        last_call=now - pd.Timedelta(days=1),
    )
    serve.model_cache["models:/Demo/2"] = serve.ModelCacheEntry(
        model=object(),
        sys_path=[],
        model_uri="models:/Demo/2",
        last_call=now,
    )

    evicted = serve._evict_cache(now=now)
    assert evicted["ttl"] == ["models:/Demo/old"]
    assert evicted["lru"] == ["models:/Demo/1"]
    assert set(serve.model_cache) == {"models:/Demo@champion", "models:/Demo/2"}
    assert serve.model_cache["models:/Demo@champion"].is_alias_uri is True

    cache_response = serve.list_cached_models()
    assert cache_response["cache"] == {"max_models": 2, "ttl_days": 10.0}
    assert len(cache_response["cached_models"]) == 2


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
