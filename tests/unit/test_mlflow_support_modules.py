from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from prometheus_client import generate_latest

from mlox.services.mlflow import mlops
from mlox.services.mlflow_gateway import serve
from mlox.services.otel.client import OTelClient


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


def _test_telemetry_client(provider: TracerProvider) -> OTelClient:
    client = object.__new__(OTelClient)
    client.tracer = provider.get_tracer("mlox.mlflow_gateway.test")
    return client


def _model_telemetry_client(provider: TracerProvider):
    client = _test_telemetry_client(provider)
    client.metrics = []
    client.histograms = []
    client.logs = []
    client.send_metric = lambda name, value, attributes=None: client.metrics.append(
        (name, value, attributes)
    )
    client.send_histogram = (
        lambda name, value, attributes=None, **kwargs: client.histograms.append(
            (name, value, attributes, kwargs)
        )
    )
    client.send_log = (
        lambda message, severity="INFO", attributes=None: client.logs.append(
            (message, severity, attributes)
        )
    )
    return client


class _TrackedModel(mlops.DeployableModel):
    def tracked_training(self, params=None):
        return {"artifact": "value"}

    def live_predict(self, input, params=None, artifacts=None):
        return pd.DataFrame({"y": [1 for _ in range(len(input))]})


def test_deployable_model_optional_runtime_providers(monkeypatch):
    model = _TrackedModel()
    monkeypatch.delenv(mlops.SECRET_MANAGER_KEYFILE_ENV, raising=False)
    monkeypatch.delenv(mlops.SECRET_MANAGER_KEYFILE_PW_ENV, raising=False)
    monkeypatch.setattr(mlops, "get_process_telemetry_client", lambda: None)

    assert model.get_secret_manager() is None
    assert model.get_telemetry_client() is None

    manager = object()
    monkeypatch.setenv(mlops.SECRET_MANAGER_KEYFILE_ENV, "encrypted")
    monkeypatch.setenv(mlops.SECRET_MANAGER_KEYFILE_PW_ENV, "password")
    monkeypatch.setattr(mlops, "load_secret_manager_from_env", lambda: manager)

    assert model.get_secret_manager() is manager

    with pytest.raises(ValueError, match="Model step names"):
        with model.model_step("invalid/step"):
            pass


def test_mlops_predict_emits_hierarchical_pipeline_spans(monkeypatch):
    monkeypatch.setenv("MLFLOW_URI", "https://mlflow.local")
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = _model_telemetry_client(provider)
    monkeypatch.setattr(
        mlops,
        "get_process_telemetry_client",
        lambda: telemetry,
    )

    class _PipelineModel(_TrackedModel):
        def live_predict(self, input, params=None, artifacts=None):
            with self.model_step("pipeline"):
                with self.model_step("input.normalize") as step:
                    normalized = np.asarray(input, dtype=float) / 2.0
                    step.observe_array("output", normalized)
                with self.model_step(
                    "pca.transform",
                    component="PCA",
                    component_version=2,
                ) as step:
                    transformed = normalized[:, :1] * 3.0
                    step.observe_array("output", transformed)
                with self.model_step(
                    "regression.predict",
                    component="LinearRegression",
                    component_version=1,
                ):
                    prediction = transformed + 1.0
            return pd.DataFrame({"prediction": prediction[:, 0]})

    service = mlops.MLFlowDeployableModelService(_PipelineModel(), "LR")
    invocation = mlops.ModelInvocationContext(
        pipeline_id="pipeline-run-1",
        pipeline_name="pca-lr",
        request_id="request-1",
        model_name="LR",
        model_version="4",
        model_alias="champion",
    )
    with mlops.model_invocation_context(invocation):
        result = service.predict(None, np.array([[2.0, 4.0], [6.0, 8.0]]))

    assert result["prediction"].tolist() == [4.0, 10.0]
    spans = exporter.get_finished_spans()
    root = next(span for span in spans if span.name == "mlox.model.live_predict")
    steps = {
        span.attributes["mlox.step.path"]: span
        for span in spans
        if span.name == "mlox.model.step"
    }
    pipeline = steps["LR/pipeline"]
    normalized = steps["LR/pipeline/input.normalize"]
    pca = steps["LR/pipeline/pca.transform"]
    regression = steps["LR/pipeline/regression.predict"]

    assert pipeline.parent.span_id == root.context.span_id
    assert normalized.parent.span_id == pipeline.context.span_id
    assert pca.parent.span_id == pipeline.context.span_id
    assert regression.parent.span_id == pipeline.context.span_id
    assert pca.attributes["mlox.component.version"] == "2"
    assert pca.attributes["mlox.observation.output.mean"] == 6.0
    assert pca.attributes["mlox.pipeline.id"] == "pipeline-run-1"
    assert telemetry.metrics[0][0] == "mlox.model.predictions"
    assert telemetry.histograms[0][0] == "mlox.model.prediction.duration"
    assert telemetry.logs[0][1] == "INFO"
    assert mlops.current_model_invocation() is None


def test_deployable_model_propagates_trace_and_pipeline_headers(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = _model_telemetry_client(provider)
    monkeypatch.setattr(
        mlops,
        "get_process_telemetry_client",
        lambda: telemetry,
    )
    invocation = mlops.ModelInvocationContext(
        pipeline_id="pipeline-1",
        pipeline_name="pca-lr",
        request_id="request-1",
        model_name="LR",
        model_version="1",
    )

    with mlops.model_invocation_context(invocation):
        with telemetry.span("outbound", kind="client"):
            headers = _TrackedModel().get_outbound_headers()

    assert headers[mlops.PIPELINE_ID_HEADER] == "pipeline-1"
    assert headers[mlops.PIPELINE_NAME_HEADER] == "pca-lr"
    assert headers["traceparent"].startswith("00-")


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

    monkeypatch.setattr(
        mlops.mlflow, "set_tracking_uri", lambda v: calls["set_tracking_uri"].append(v)
    )
    monkeypatch.setattr(
        mlops.mlflow, "set_registry_uri", lambda v: calls["set_registry_uri"].append(v)
    )
    monkeypatch.setattr(mlops.mlflow, "set_experiment", lambda *_: None)
    monkeypatch.setattr(mlops.mlflow, "start_run", lambda **_kwargs: _cm_empty())
    monkeypatch.setattr(
        mlops.mlflow, "start_span", lambda *_args, **_kwargs: _cm_span()
    )
    monkeypatch.setattr(
        mlops.mlflow.models, "infer_signature", lambda *_args, **_kwargs: "sig"
    )
    monkeypatch.setattr(
        mlops.mlflow, "set_tag", lambda k, v: calls["set_tag"].append((k, v))
    )

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
    alias_calls = []

    class _Client:
        def set_registered_model_alias(self, name, alias, version):
            alias_calls.append((name, alias, version))

    monkeypatch.setattr(mlops, "MlflowClient", _Client)

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
    assert alias_calls == []

    svc.set_alias("champion")
    assert alias_calls == [("demo-registry", "champion", "7")]

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


def test_mlops_set_alias_is_not_applied_without_registered_version(monkeypatch):
    monkeypatch.setenv("MLFLOW_URI", "https://mlflow.local")
    svc = mlops.MLFlowDeployableModelService(
        model=_TrackedModel(),
        model_class="DemoModel",
    )

    alias_calls = []

    class _Client:
        def set_registered_model_alias(self, name, alias, version):
            alias_calls.append((name, alias, version))

    monkeypatch.setattr(mlops, "MlflowClient", _Client)

    svc.set_alias("champion")
    assert alias_calls == []


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


def test_mlops_prepared_code_paths_exclude_cache_directories(monkeypatch, tmp_path):
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

    monkeypatch.setattr(
        serve.mlflow.pyfunc, "load_model", lambda model_uri: _LoadedModel()
    )
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
    parsed, cached, resolved = serve.runandget(req)
    assert cached is False
    assert parsed[0]["result"] == 3.0
    assert resolved.resolved_model_uri == "models:/Demo/1"

    parsed2, cached2, resolved2 = serve.runandget(req)
    assert cached2 is True
    assert parsed2[0]["result"] == 3.0
    assert resolved2.resolved_model_uri == "models:/Demo/1"
    cache = serve.list_cached_models()["cached_models"]
    assert cache[0]["model_uri"] == "models:/Demo/1"
    assert serve.clear_cached_models()["cleared_models_count"] == 1
    assert serve.model_cache == {}

    response = serve.predict(req)
    assert response["is_cached_model"] is False
    assert response["prediction_time_sec"] >= 0
    assert response["model"]["resolved_model_uri"] == "models:/Demo/1"

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


def test_serve_exposes_prometheus_metrics_and_request_ids():
    client = TestClient(serve.app)

    generated_id_response = client.get("/health")
    supplied_id_response = client.get(
        "/health", headers={serve.REQUEST_ID_HEADER: "request-from-client"}
    )
    metrics_response = client.get("/metrics")

    assert generated_id_response.status_code == 200
    assert generated_id_response.headers[serve.REQUEST_ID_HEADER]
    assert generated_id_response.headers[mlops.PIPELINE_ID_HEADER]
    assert (
        supplied_id_response.headers[serve.REQUEST_ID_HEADER] == "request-from-client"
    )
    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith("text/plain")
    assert "mlox_gateway_http_requests_total" in metrics_response.text
    assert "mlox_gateway_http_request_duration_seconds" in metrics_response.text
    assert "mlox_gateway_model_cache_entries" in metrics_response.text


def test_gateway_injects_resolved_model_invocation_context(monkeypatch):
    captured = {}

    class _LoadedModel:
        def predict(self, input_data, params=None):
            captured["context"] = mlops.current_model_invocation()
            return pd.DataFrame({"prediction": [1.0]})

    monkeypatch.setattr(serve, "_load_model", lambda _uri: (_LoadedModel(), False))
    client = TestClient(serve.app)
    response = client.post(
        "/prod/predict",
        headers={
            mlops.PIPELINE_ID_HEADER: "pipeline-run-42",
            mlops.PIPELINE_NAME_HEADER: "pca-lr",
            serve.REQUEST_ID_HEADER: "request-42",
        },
        json={
            "input_data": [[1.0, 2.0]],
            "registry_model_name": "LR",
            "registry_model_version": 7,
        },
    )

    assert response.status_code == 200
    assert response.headers[mlops.PIPELINE_ID_HEADER] == "pipeline-run-42"
    assert response.headers[mlops.PIPELINE_NAME_HEADER] == "pca-lr"
    invocation = captured["context"]
    assert invocation.pipeline_id == "pipeline-run-42"
    assert invocation.pipeline_name == "pca-lr"
    assert invocation.request_id == "request-42"
    assert invocation.model_name == "LR"
    assert invocation.model_version == "7"
    assert mlops.current_model_invocation() is None


def test_serve_propagates_trace_context_and_records_http_span(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(serve, "TELEMETRY_CLIENT", _test_telemetry_client(provider))
    trace_id = "0af7651916cd43dd8448eb211c80319c"
    client = TestClient(serve.app)

    response = client.get(
        "/health",
        headers={
            "traceparent": f"00-{trace_id}-b7ad6b7169203331-01",
        },
    )

    assert response.status_code == 200
    assert response.headers[serve.TRACE_ID_HEADER] == trace_id
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert format(spans[0].context.trace_id, "032x") == trace_id
    assert spans[0].attributes["http.route"] == "/health"


def test_serve_prediction_span_contains_resolved_model_identity(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(serve, "TELEMETRY_CLIENT", _test_telemetry_client(provider))
    monkeypatch.setattr(
        serve,
        "_predict",
        lambda _data: {
            "data": [{"prediction": 1}],
            "is_cached_model": True,
            "model": {
                "resolved_model_version": "7",
                "resolved_model_uri": "models:/Demo/7",
            },
        },
    )
    request = serve.PredictionRequest(
        input_data=[[1.0]],
        registry_model_name="Demo",
        registry_model_alias="champion",
    )

    serve.predict(request)

    span = exporter.get_finished_spans()[0]
    assert span.name == "model.predict"
    assert span.attributes["mlox.model.name"] == "Demo"
    assert span.attributes["mlox.model.requested_alias"] == "champion"
    assert span.attributes["mlox.model.version"] == "7"
    assert span.attributes["mlox.model.cache_hit"] is True


def test_serve_records_prediction_and_model_cache_metrics(monkeypatch):
    serve.clear_cached_models()

    class _LoadedModel:
        def predict(self, input_data, params=None):
            return pd.DataFrame({"result": [float(np.sum(input_data))]})

    monkeypatch.setattr(
        serve.mlflow.pyfunc, "load_model", lambda model_uri: _LoadedModel()
    )
    monkeypatch.setattr(
        serve.mlflow.artifacts, "download_artifacts", lambda *_a, **_k: ""
    )
    request = serve.PredictionRequest(
        input_data=[[2.0, 3.0]],
        registry_model_name="MetricsDemo",
        registry_model_version=42,
    )

    first = serve.predict(request)
    second = serve.predict(request)
    output = generate_latest().decode("utf-8")

    assert first["is_cached_model"] is False
    assert second["is_cached_model"] is True
    assert 'mlox_gateway_model_cache_operations_total{result="miss"}' in output
    assert 'mlox_gateway_model_cache_operations_total{result="hit"}' in output
    assert (
        'mlox_gateway_predictions_total{model="MetricsDemo",model_cache_hit="false",'
        'status="success",version="42"}' in output
    )
    assert (
        'mlox_gateway_model_first_request_timestamp_seconds{model="MetricsDemo",'
        'version="42"}' in output
    )
    assert (
        'mlox_gateway_model_last_request_timestamp_seconds{model="MetricsDemo",'
        'version="42"}' in output
    )


def test_serve_model_reference_supports_version_or_alias(monkeypatch):
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

    class _Client:
        def get_model_version_by_alias(self, name, alias):
            assert name == "Demo"
            assert alias == "champion"
            return SimpleNamespace(version="7")

    monkeypatch.setattr(serve.mlflow, "MlflowClient", _Client)

    version_ref = serve._resolve_model_reference(version_req)
    alias_ref = serve._resolve_model_reference(alias_req)

    assert version_ref.resolved_model_uri == "models:/Demo/1"
    assert version_ref.resolved_model_version == "1"
    assert version_ref.requested_model_alias is None
    assert alias_ref.resolved_model_uri == "models:/Demo/7"
    assert alias_ref.resolved_model_version == "7"
    assert alias_ref.requested_model_alias == "champion"

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


def test_serve_supports_dataframe_split_input():
    req = serve.PredictionRequest(
        dataframe_split={
            "columns": [
                "interested_party_id",
                "event_id",
                "top_k",
                "filter_event_ids",
            ],
            "data": [
                [
                    "9a44ed51-17f9-47c8-afd6-3e73f8a6dcc3",
                    "f8c4f629-dcea-4aad-993c-3affc892a3a5",
                    20,
                    '["b67e9ed2-0df7-4840-959a-e55d14cf82a2"]',
                ]
            ],
        },
        registry_model_name="Demo",
        registry_model_version=1,
    )

    model_input = serve._prediction_input(req)
    assert isinstance(model_input, pd.DataFrame)
    assert list(model_input.columns) == [
        "interested_party_id",
        "event_id",
        "top_k",
        "filter_event_ids",
    ]
    assert model_input.iloc[0]["top_k"] == 20

    with pytest.raises(ValueError):
        serve.PredictionRequest(
            input_data=[[1.0]],
            dataframe_split={"columns": ["a"], "data": [[1.0]]},
            registry_model_name="Demo",
            registry_model_version=1,
        )
    with pytest.raises(ValueError):
        serve.PredictionRequest(
            registry_model_name="Demo",
            registry_model_version=1,
        )
    with pytest.raises(ValueError):
        serve.PredictionRequest(
            dataframe_split={"columns": ["a", "b"], "data": [[1.0]]},
            registry_model_name="Demo",
            registry_model_version=1,
        )


def test_serve_forwards_params_with_dataframe_split(monkeypatch):
    serve.model_cache.clear()
    seen = {}

    class _LoadedModel:
        def predict(self, input_data, params=None):
            seen["input_data"] = input_data
            seen["params"] = params
            return pd.DataFrame({"value": [params["top_k"]]})

    monkeypatch.setattr(
        serve.mlflow.pyfunc, "load_model", lambda model_uri: _LoadedModel()
    )
    monkeypatch.setattr(
        serve.mlflow.artifacts,
        "download_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")),
    )

    req = serve.PredictionRequest(
        dataframe_split={
            "columns": ["interested_party_id", "event_id"],
            "data": [["party-1", "event-1"]],
        },
        params={"top_k": 20, "include_scores": True},
        registry_model_name="Demo",
        registry_model_version=1,
    )

    parsed, cached, resolved = serve.runandget(req)

    assert cached is False
    assert parsed == [{"value": 20}]
    assert resolved.resolved_model_uri == "models:/Demo/1"
    assert isinstance(seen["input_data"], pd.DataFrame)
    assert seen["input_data"].iloc[0].to_dict() == {
        "interested_party_id": "party-1",
        "event_id": "event-1",
    }
    assert seen["params"] == {"top_k": 20, "include_scores": True}


def test_serve_alias_requests_cache_resolved_model_versions(monkeypatch):
    serve.model_cache.clear()

    class _LoadedModel:
        def __init__(self, model_uri):
            self.model_uri = model_uri

        def predict(self, input_data, params=None):
            return pd.DataFrame({"model_uri": [self.model_uri]})

    class _Client:
        version = "2"

        def get_model_version_by_alias(self, name, alias):
            return SimpleNamespace(version=self.version)

    client = _Client()
    monkeypatch.setattr(serve.mlflow, "MlflowClient", lambda: client)
    monkeypatch.setattr(
        serve.mlflow.pyfunc,
        "load_model",
        lambda model_uri: _LoadedModel(model_uri),
    )
    monkeypatch.setattr(
        serve.mlflow.artifacts,
        "download_artifacts",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")),
    )

    req = serve.PredictionRequest(
        input_data=[[1.0]],
        registry_model_name="Demo",
        registry_model_alias="champion",
    )

    parsed, cached, resolved = serve.runandget(req)
    assert cached is False
    assert parsed[0]["model_uri"] == "models:/Demo/2"
    assert resolved.resolved_model_uri == "models:/Demo/2"
    assert set(serve.model_cache) == {"models:/Demo/2"}

    client.version = "3"
    parsed2, cached2, resolved2 = serve.runandget(req)
    assert cached2 is False
    assert parsed2[0]["model_uri"] == "models:/Demo/3"
    assert resolved2.resolved_model_uri == "models:/Demo/3"
    assert set(serve.model_cache) == {"models:/Demo/2", "models:/Demo/3"}


def test_serve_cache_evicts_by_ttl_and_lru(monkeypatch):
    serve.model_cache.clear()
    monkeypatch.setenv("MLOX_GATEWAY_CACHE_MAX_MODELS", "2")
    monkeypatch.setenv("MLOX_GATEWAY_CACHE_TTL_DAYS", "10")

    now = datetime.now()
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
    serve.model_cache["models:/Demo/3"] = serve.ModelCacheEntry(
        model=object(),
        sys_path=[],
        model_uri="models:/Demo/3",
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
    assert set(serve.model_cache) == {"models:/Demo/3", "models:/Demo/2"}
    assert serve.model_cache["models:/Demo/3"].is_alias_uri is False

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

    monkeypatch.setattr(
        serve,
        "runandget",
        lambda _req: (_ for _ in ()).throw(_RestException("missing")),
    )
    try:
        serve.predict(req)
        assert False, "Expected HTTPException for missing model"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404

    monkeypatch.setattr(
        serve, "runandget", lambda _req: (_ for _ in ()).throw(ValueError("bad input"))
    )
    try:
        serve.predict(req)
        assert False, "Expected HTTPException for invalid input"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400

    monkeypatch.setattr(
        serve, "runandget", lambda _req: (_ for _ in ()).throw(RuntimeError("boom"))
    )
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
