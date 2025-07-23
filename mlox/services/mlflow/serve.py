import os
import sys
import json
import mlflow  # type: ignore
import numpy as np
import pandas as pd

from typing import List, Dict, Any

from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

SYS_PATH = sys.path


class ModelCacheEntry(BaseModel):
    model: Any
    sys_path: List[str]
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
app = FastAPI()
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
    }


class PredictionRequest(BaseModel):
    input_data: List
    params: Dict | None = None
    registry_model_name: str | None = None
    registry_model_version: int | None = None


def runandget(data: PredictionRequest):
    print("sys.path.BEFORE", SYS_PATH, flush=True)
    print("Input data: ", data)
    print("Input model_name: ", data.registry_model_name)
    print("Input model_version: ", data.registry_model_version)

    # Assuming your 'run_databricks_model' function and input handling are correct
    model_uri = f"models:/{data.registry_model_name}/{data.registry_model_version}"
    print(f"Load model from = {model_uri}")

    model_uri = f"models:/{data.registry_model_name}/{data.registry_model_version}"
    is_cached_model = False
    if model_uri not in model_cache:
        loaded_model = mlflow.pyfunc.load_model(model_uri=model_uri)
        model_cache[model_uri] = ModelCacheEntry(model=loaded_model, sys_path=sys.path)
    else:
        mce = model_cache[model_uri]
        mce.last_call = datetime.now()
        mce.num_calls += 1
        loaded_model = mce.model
        sys.path = mce.sys_path
        is_cached_model = True

    print("Model loaded: ", loaded_model)
    input_data = np.array(data.input_data)
    print("Model data: ", input_data)
    print("Model params: ", data.params)
    df_pred = loaded_model.predict(input_data, params=data.params)
    print("Model prediction: ", df_pred)

    # Proper JSON serialization
    if not isinstance(df_pred, pd.DataFrame):
        df_pred = pd.DataFrame(df_pred)
    parsed = json.loads(df_pred.to_json(orient="records", date_format="iso"))

    print("sys.path.BEFORE", SYS_PATH)
    print("sys.path.AFTER", sys.path)
    # reset sys_path
    sys.path = list(SYS_PATH)
    print("sys.path.RESET", sys.path)
    # Returning JSON response properly
    return parsed, is_cached_model


@app.post("/prod/predict")
def predict(data: PredictionRequest):
    try:
        prediction_time = datetime.now()
        data, is_cached_model = runandget(data)

        prediction_tdelta = datetime.now() - prediction_time
        return {
            "data": data,
            "prediction_time_sec": prediction_tdelta.seconds,
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
    print("Model name: ", model_name)
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
