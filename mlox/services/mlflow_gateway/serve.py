import os
import sys
import json
import logging
import threading
import time
import uuid
import mlflow  # type: ignore
import numpy as np
import pandas as pd

from contextvars import ContextVar
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SYS_PATH = list(sys.path)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


DEFAULT_CACHE_MAX_MODELS = 10
DEFAULT_CACHE_TTL_DAYS = 10.0
REQUEST_ID_HEADER = "X-Request-ID"
request_id_context: ContextVar[str] = ContextVar("request_id", default="")
model_first_request_keys: set[tuple[str, str]] = set()
model_first_request_lock = threading.Lock()

HTTP_REQUESTS = Counter(
    "mlox_gateway_http_requests_total",
    "HTTP requests handled by the gateway.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "mlox_gateway_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "mlox_gateway_http_requests_in_progress",
    "HTTP requests currently being processed.",
    ("method",),
)
PREDICTIONS = Counter(
    "mlox_gateway_predictions_total",
    "Predictions handled by model, version, status, and model-cache result.",
    ("model", "version", "status", "model_cache_hit"),
)
PREDICTION_DURATION = Histogram(
    "mlox_gateway_prediction_duration_seconds",
    "End-to-end prediction duration in seconds.",
    ("model", "version"),
)
MODEL_REQUEST_FIRST = Gauge(
    "mlox_gateway_model_first_request_timestamp_seconds",
    "Unix timestamp of the first request observed for a model version.",
    ("model", "version"),
)
MODEL_REQUEST_LAST = Gauge(
    "mlox_gateway_model_last_request_timestamp_seconds",
    "Unix timestamp of the latest request observed for a model version.",
    ("model", "version"),
)
MODEL_CACHE_OPERATIONS = Counter(
    "mlox_gateway_model_cache_operations_total",
    "Model-cache lookups by result.",
    ("result",),
)
MODEL_CACHE_EVICTIONS = Counter(
    "mlox_gateway_model_cache_evictions_total",
    "Model-cache evictions by reason.",
    ("reason",),
)
MODEL_CACHE_ENTRIES = Gauge(
    "mlox_gateway_model_cache_entries",
    "Models currently held in the process-local cache.",
)
MODEL_LOADS = Counter(
    "mlox_gateway_model_loads_total",
    "Model load attempts by status.",
    ("status",),
)
MODEL_LOAD_DURATION = Histogram(
    "mlox_gateway_model_load_duration_seconds",
    "MLflow model load duration in seconds.",
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid integer for %s; using default %s", name, default)
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid float for %s; using default %s", name, default)
        return default


def _cache_settings() -> Dict[str, int | float]:
    return {
        "max_models": max(
            1,
            _env_int("MLOX_GATEWAY_CACHE_MAX_MODELS", DEFAULT_CACHE_MAX_MODELS),
        ),
        "ttl_days": max(
            0.0,
            _env_float("MLOX_GATEWAY_CACHE_TTL_DAYS", DEFAULT_CACHE_TTL_DAYS),
        ),
    }


class ModelCacheEntry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: Any
    sys_path: List[str]
    model_uri: str
    requirements: List[str] = Field(default_factory=list)
    num_calls: int = Field(default=0)
    loaded_at: datetime = Field(default_factory=datetime.now)
    last_call: datetime = Field(default_factory=datetime.now)
    first_call: datetime = Field(default_factory=datetime.now)

    @property
    def is_alias_uri(self) -> bool:
        return "@" in self.model_uri.rsplit("/", 1)[-1]


model_cache: Dict[str, ModelCacheEntry] = dict()

# os.environ["HOST"] = read_secret_as_yaml("DATABRICKS").get(
#     "DATABRICKS_URL", None
# )
# os.environ["DATABRICKS_TOKEN"] = read_secret_as_yaml("DATABRICKS").get(
#     "DATABRICKS_TOKEN", None
# )
os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

mlflow.set_tracking_uri(os.environ.get("MLFLOW_URI", None))
mlflow.set_registry_uri(os.environ.get("MLFLOW_URI", None))

# CORS middleware settings
app = FastAPI(title="mlox MLflow Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observe_http_request(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    status_code = 500
    HTTP_REQUESTS_IN_PROGRESS.labels(request.method).inc()
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        duration = time.perf_counter() - started
        HTTP_REQUESTS.labels(request.method, route_path, str(status_code)).inc()
        HTTP_REQUEST_DURATION.labels(request.method, route_path).observe(duration)
        HTTP_REQUESTS_IN_PROGRESS.labels(request.method).dec()
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "route": route_path,
                    "status": status_code,
                    "duration_sec": round(duration, 6),
                }
            )
        )
        request_id_context.reset(token)


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    _evict_cache()
    return {
        "timestamp": datetime.now().isoformat(),
        "cached_models_count": len(model_cache),
        "tracking_uri": mlflow.get_tracking_uri(),
        "registry_uri": mlflow.get_registry_uri(),
        "cache": _cache_settings(),
    }


class DataFrameSplit(BaseModel):
    columns: List[str]
    data: List[List[Any]]
    index: List[Any] | None = None

    @model_validator(mode="after")
    def _validate_rows_match_columns(self):
        expected = len(self.columns)
        for row in self.data:
            if len(row) != expected:
                raise ValueError(
                    "Each dataframe_split row must have the same length as columns"
                )
        return self


class PredictionRequest(BaseModel):
    input_data: List | None = None
    dataframe_split: DataFrameSplit | None = None
    params: Dict | None = None
    registry_model_name: str
    registry_model_version: int | str | None = None
    registry_model_alias: str | None = None

    @field_validator("registry_model_name")
    @classmethod
    def _model_name_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("registry_model_name must not be empty")
        return value

    @field_validator("registry_model_alias")
    @classmethod
    def _model_alias_must_not_be_empty(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("registry_model_alias must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_request_shape(self):
        has_version = self.registry_model_version is not None
        has_alias = self.registry_model_alias is not None
        if has_version == has_alias:
            raise ValueError(
                "Provide exactly one of registry_model_version or registry_model_alias"
            )
        has_input_data = self.input_data is not None
        has_dataframe_split = self.dataframe_split is not None
        if has_input_data == has_dataframe_split:
            raise ValueError("Provide exactly one of input_data or dataframe_split")
        return self


class ResolvedModelReference(BaseModel):
    requested_model_name: str
    requested_model_version: str | None = None
    requested_model_alias: str | None = None
    resolved_model_version: str
    resolved_model_uri: str


def _resolve_model_reference(data: PredictionRequest) -> ResolvedModelReference:
    if data.registry_model_alias is not None:
        client = mlflow.MlflowClient()
        model_version = client.get_model_version_by_alias(
            name=data.registry_model_name,
            alias=data.registry_model_alias,
        )
        resolved_version = str(model_version.version)
        return ResolvedModelReference(
            requested_model_name=data.registry_model_name,
            requested_model_alias=data.registry_model_alias,
            resolved_model_version=resolved_version,
            resolved_model_uri=f"models:/{data.registry_model_name}/{resolved_version}",
        )

    resolved_version = str(data.registry_model_version)
    return ResolvedModelReference(
        requested_model_name=data.registry_model_name,
        requested_model_version=resolved_version,
        resolved_model_version=resolved_version,
        resolved_model_uri=f"models:/{data.registry_model_name}/{resolved_version}",
    )


def _prediction_input(data: PredictionRequest) -> np.ndarray | pd.DataFrame:
    if data.dataframe_split is not None:
        return pd.DataFrame(
            data.dataframe_split.data,
            columns=data.dataframe_split.columns,
            index=data.dataframe_split.index,
        )
    return np.array(data.input_data)


def _read_requirements(model_uri: str) -> List[str]:
    try:
        artifact_path = mlflow.artifacts.download_artifacts(model_uri)
    except Exception as exc:
        logger.info(
            "Could not download model artifacts for requirement inspection: %s", exc
        )
        return []

    req_file = Path(artifact_path) / "requirements.txt"
    if not req_file.exists():
        return []
    try:
        return [
            line.strip()
            for line in req_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    except OSError as exc:
        logger.info("Could not read model requirements from %s: %s", req_file, exc)
        return []


def _evict_cache(
    *, protected_uri: str | None = None, now: datetime | None = None
) -> Dict[str, List[str]]:
    settings = _cache_settings()
    max_models = int(settings["max_models"])
    ttl_days = float(settings["ttl_days"])
    now = now or datetime.now()
    evicted: Dict[str, List[str]] = {"ttl": [], "lru": []}

    if ttl_days > 0:
        expires_before = now - timedelta(days=ttl_days)
        for uri, entry in list(model_cache.items()):
            if uri == protected_uri:
                continue
            if entry.last_call < expires_before:
                model_cache.pop(uri, None)
                evicted["ttl"].append(uri)
                MODEL_CACHE_EVICTIONS.labels("ttl").inc()

    while len(model_cache) > max_models:
        candidates = [
            (uri, entry)
            for uri, entry in model_cache.items()
            if uri != protected_uri
        ]
        if not candidates:
            break
        uri, _ = min(candidates, key=lambda item: item[1].last_call)
        model_cache.pop(uri, None)
        evicted["lru"].append(uri)
        MODEL_CACHE_EVICTIONS.labels("lru").inc()

    MODEL_CACHE_ENTRIES.set(len(model_cache))
    if evicted["ttl"] or evicted["lru"]:
        logger.info("Evicted cache entries: %s", evicted)
    return evicted


def _load_model(model_uri: str) -> tuple[Any, bool]:
    _evict_cache(protected_uri=model_uri)
    if model_uri not in model_cache:
        MODEL_CACHE_OPERATIONS.labels("miss").inc()
        load_started = time.perf_counter()
        try:
            loaded_model = mlflow.pyfunc.load_model(model_uri=model_uri)
        except Exception:
            MODEL_LOADS.labels("error").inc()
            raise
        finally:
            MODEL_LOAD_DURATION.observe(time.perf_counter() - load_started)
        MODEL_LOADS.labels("success").inc()
        now = datetime.now()
        model_cache[model_uri] = ModelCacheEntry(
            model=loaded_model,
            model_uri=model_uri,
            sys_path=list(sys.path),
            requirements=_read_requirements(model_uri),
            num_calls=1,
            loaded_at=now,
            first_call=now,
            last_call=now,
        )
        MODEL_CACHE_ENTRIES.set(len(model_cache))
        _evict_cache(protected_uri=model_uri)
        return loaded_model, False

    MODEL_CACHE_OPERATIONS.labels("hit").inc()
    mce = model_cache[model_uri]
    mce.last_call = datetime.now()
    mce.num_calls += 1
    sys.path = list(mce.sys_path)
    return mce.model, True


def runandget(data: PredictionRequest):
    resolved_model = _resolve_model_reference(data)
    model_uri = resolved_model.resolved_model_uri

    loaded_model, is_cached_model = _load_model(model_uri)
    input_data = _prediction_input(data)
    df_pred = loaded_model.predict(input_data, params=data.params)

    # Proper JSON serialization
    if not isinstance(df_pred, pd.DataFrame):
        df_pred = pd.DataFrame(df_pred)
    parsed = json.loads(df_pred.to_json(orient="records", date_format="iso"))

    sys.path = list(SYS_PATH)
    _evict_cache(protected_uri=model_uri)
    return parsed, is_cached_model, resolved_model


@app.post("/prod/predict")
def predict(data: PredictionRequest):
    started = time.perf_counter()
    model_name = data.registry_model_name
    model_version = "unresolved"
    cache_hit = "unknown"
    try:
        prediction_time = datetime.now()
        data, is_cached_model, resolved_model = runandget(data)
        model_version = resolved_model.resolved_model_version
        cache_hit = str(is_cached_model).lower()
        now = time.time()
        model_key = (model_name, model_version)
        with model_first_request_lock:
            if model_key not in model_first_request_keys:
                MODEL_REQUEST_FIRST.labels(*model_key).set(now)
                model_first_request_keys.add(model_key)
        MODEL_REQUEST_LAST.labels(model_name, model_version).set(now)
        PREDICTIONS.labels(model_name, model_version, "success", cache_hit).inc()

        prediction_tdelta = datetime.now() - prediction_time
        logger.info(
            json.dumps(
                {
                    "event": "prediction",
                    "request_id": request_id_context.get(),
                    "model": model_name,
                    "version": model_version,
                    "model_cache_hit": is_cached_model,
                    "duration_sec": round(prediction_tdelta.total_seconds(), 6),
                    "status": "success",
                }
            )
        )
        return {
            "data": data,
            "prediction_time_sec": prediction_tdelta.total_seconds(),
            "is_cached_model": is_cached_model,
            "model": resolved_model.model_dump(),
        }
    except mlflow.exceptions.RestException as e:
        PREDICTIONS.labels(model_name, model_version, "not_found", cache_hit).inc()
        sys.path = list(SYS_PATH)
        raise HTTPException(status_code=404, detail=f"Model not found: {str(e)}")
    except ValueError as ve:
        PREDICTIONS.labels(model_name, model_version, "invalid_input", cache_hit).inc()
        sys.path = list(SYS_PATH)
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(ve)}")
    except Exception as e:
        PREDICTIONS.labels(model_name, model_version, "error", cache_hit).inc()
        sys.path = list(SYS_PATH)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        PREDICTION_DURATION.labels(model_name, model_version).observe(
            time.perf_counter() - started
        )


@app.get("/model/{model_name}/list")
def list_models(model_name: str):
    logger.info(f"Model name: {model_name}")
    client = mlflow.MlflowClient()

    res_list = list()
    filter_string = f"name='{model_name}'"
    for rm in client.search_model_versions(filter_string):
        uri = f"models:/{model_name}/{rm.version}"
        out = {
            "model": model_name,
            "version": rm.version,
            "creation_timestamp": rm.creation_timestamp,
            "run_id": rm.run_id,
            "tags": rm.tags,
            "descr": rm.description,
            "cache_status": "not cached" if uri not in model_cache else "cached",
            "cache_num_calls": 0
            if uri not in model_cache
            else model_cache[uri].num_calls,
            "cache_first_call": -1
            if uri not in model_cache
            else model_cache[uri].first_call,
            "cache_last_call": -1
            if uri not in model_cache
            else model_cache[uri].last_call,
        }
        res_list.append(out)
    return {"model": model_name, "versions": res_list}


@app.get("/cache")
def list_cached_models():
    _evict_cache()
    now = datetime.now()
    return {
        "cache": _cache_settings(),
        "cached_models": [
            {
                "model_uri": key,
                "is_alias_uri": entry.is_alias_uri,
                "num_calls": entry.num_calls,
                "loaded_at": entry.loaded_at.isoformat(),
                "first_call": entry.first_call.isoformat(),
                "last_call": entry.last_call.isoformat(),
                "age_days": (now - entry.loaded_at).total_seconds() / 86400,
                "idle_days": (now - entry.last_call).total_seconds() / 86400,
                "requirements": entry.requirements,
            }
            for key, entry in model_cache.items()
        ]
    }


@app.delete("/cache")
def clear_cached_models():
    count = len(model_cache)
    model_cache.clear()
    MODEL_CACHE_ENTRIES.set(0)
    sys.path = list(SYS_PATH)
    return {"cleared_models_count": count}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=8080, host="127.0.0.1")

"""
curl -X POST http://localhost:8080/prod/predict \
     -H "Content-Type: application/json" \
     -d '{
           "input_data": [["2024-04-15"]], "params": {"my_param": true}, "registry_model_version": 2, "registry_model_name": "Test"
         }'
"""

"""
curl -X POST http://localhost:8080/prod/predict \
    -H "Content-Type: application/json" \
    -d '{
        "input_data": [[1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0]], "params": {"my_param": true}, "registry_model_version": 1, "registry_model_name": "Test"
        }'
"""
