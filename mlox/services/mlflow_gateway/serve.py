import os
import sys
import json
import logging
import mlflow  # type: ignore
import numpy as np
import pandas as pd

from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

SYS_PATH = list(sys.path)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class ModelCacheEntry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: Any
    sys_path: List[str]
    model_uri: str
    requirements: List[str] = Field(default_factory=list)
    num_calls: int = Field(default=0)
    last_call: datetime = Field(default_factory=datetime.now)
    first_call: datetime = Field(default_factory=datetime.now)


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


@app.get("/health")
def health():
    return {
        "timestamp": datetime.now().isoformat(),
        "cached_models_count": len(model_cache),
        "tracking_uri": mlflow.get_tracking_uri(),
        "registry_uri": mlflow.get_registry_uri(),
    }


class PredictionRequest(BaseModel):
    input_data: List
    params: Dict | None = None
    registry_model_name: str
    registry_model_version: int | str

    @field_validator("registry_model_name")
    @classmethod
    def _model_name_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("registry_model_name must not be empty")
        return value


def _model_uri(data: PredictionRequest) -> str:
    return f"models:/{data.registry_model_name}/{data.registry_model_version}"


def _read_requirements(model_uri: str) -> List[str]:
    try:
        artifact_path = mlflow.artifacts.download_artifacts(model_uri)
    except Exception as exc:
        logger.info("Could not download model artifacts for requirement inspection: %s", exc)
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


def _load_model(model_uri: str) -> tuple[Any, bool]:
    if model_uri not in model_cache:
        loaded_model = mlflow.pyfunc.load_model(model_uri=model_uri)
        model_cache[model_uri] = ModelCacheEntry(
            model=loaded_model,
            model_uri=model_uri,
            sys_path=list(sys.path),
            requirements=_read_requirements(model_uri),
        )
        return loaded_model, False

    mce = model_cache[model_uri]
    mce.last_call = datetime.now()
    mce.num_calls += 1
    sys.path = list(mce.sys_path)
    return mce.model, True


def runandget(data: PredictionRequest):
    logger.info(f"sys.path.BASELINE {SYS_PATH}")
    logger.info(f"Input data: {data}")
    logger.info(f"Input model_name: {data.registry_model_name}")
    logger.info(f"Input model_version: {data.registry_model_version}")

    model_uri = _model_uri(data)
    logger.info(f"Load model from = {model_uri}")

    loaded_model, is_cached_model = _load_model(model_uri)
    logger.info(f"Model loaded: {loaded_model}")
    input_data = np.array(data.input_data)
    logger.info(f"Model data: {input_data}")
    logger.info(f"Model params: {data.params}")
    df_pred = loaded_model.predict(input_data, params=data.params)
    logger.info(f"Model prediction: {df_pred}")

    # Proper JSON serialization
    if not isinstance(df_pred, pd.DataFrame):
        df_pred = pd.DataFrame(df_pred)
    parsed = json.loads(df_pred.to_json(orient="records", date_format="iso"))

    logger.info(f"sys.path.AFTER_PREDICT {sys.path}")
    sys.path = list(SYS_PATH)
    logger.info(f"sys.path.RESET {sys.path}")
    return parsed, is_cached_model


@app.post("/prod/predict")
def predict(data: PredictionRequest):
    try:
        prediction_time = datetime.now()
        data, is_cached_model = runandget(data)

        prediction_tdelta = datetime.now() - prediction_time
        return {
            "data": data,
            "prediction_time_sec": prediction_tdelta.total_seconds(),
            "is_cached_model": is_cached_model,
        }
    except mlflow.exceptions.RestException as e:
        sys.path = list(SYS_PATH)
        raise HTTPException(status_code=404, detail=f"Model not found: {str(e)}")
    except ValueError as ve:
        sys.path = list(SYS_PATH)
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(ve)}")
    except Exception as e:
        sys.path = list(SYS_PATH)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


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
    return {
        "cached_models": [
            {
                "model_uri": key,
                "num_calls": entry.num_calls,
                "first_call": entry.first_call.isoformat(),
                "last_call": entry.last_call.isoformat(),
                "requirements": entry.requirements,
            }
            for key, entry in model_cache.items()
        ]
    }


@app.delete("/cache")
def clear_cached_models():
    count = len(model_cache)
    model_cache.clear()
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
