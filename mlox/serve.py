import os
import sys
import json
import mlflow  # type: ignore
import numpy as np

from typing import List, Dict

from datetime import datetime
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

SYS_PATH = sys.path

# os.environ["HOST"] = read_secret_as_yaml("DATABRICKS").get(
#     "DATABRICKS_URL", None
# )
# os.environ["DATABRICKS_TOKEN"] = read_secret_as_yaml("DATABRICKS").get(
#     "DATABRICKS_TOKEN", None
# )
os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

mlflow.set_tracking_uri(os.environ["MLFLOW_URI"])
mlflow.set_registry_uri(os.environ["MLFLOW_URI"])

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
    return {"timestamp": datetime.now().isoformat()}


class PredictionRequest(BaseModel):
    input_data: List
    params: Dict | None = None
    registry_model_name: str | None = None
    registry_model_version: int | None = None


@app.post("/prod/predict")
def predict(data: PredictionRequest):
    try:
        print("sys.path.BEFORE", SYS_PATH, flush=True)
        prediction_time = datetime.now()
        print("Input data: ", data)
        print("Input model_name: ", data.registry_model_name)
        print("Input model_version: ", data.registry_model_version)

        # Assuming your 'run_databricks_model' function and input handling are correct
        model_uri = f"models:/{data.registry_model_name}/{data.registry_model_version}"
        print(f"Load model from = {model_uri}")
        loaded_model = mlflow.pyfunc.load_model(model_uri=model_uri)
        print("Model loaded: ", loaded_model)
        input_data = np.array(data.input_data)
        print("Model data: ", input_data)
        print("Model params: ", data.params)
        df_pred = loaded_model.predict(input_data, params=data.params)
        print("Model prediction: ", df_pred)

        # Proper JSON serialization
        parsed = json.loads(df_pred.to_json(orient="records", date_format="iso"))

        print("sys.path.BEFORE", SYS_PATH)
        print("sys.path.AFTER", sys.path)
        # reset sys_path
        sys.path = list(SYS_PATH)
        print("sys.path.RESET", sys.path)
        # Returning JSON response properly
        prediction_tdelta = datetime.now() - prediction_time
        return {"data": parsed, "prediction_time_sec": prediction_tdelta.seconds}
    except Exception as e:
        # reset sys_path
        sys.path = list(SYS_PATH)
        # Returning a more informative error message
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/model/{model_name}/list")
def list_models(model_name: str):
    print("Model name: ", model_name)
    client = mlflow.MlflowClient()

    res_list = list()
    filter_string = f"name='{model_name}'"
    for rm in client.search_model_versions(filter_string):
        out = {"model": model_name, "version": rm.version}
        out["creation_timestamp"] = rm.creation_timestamp
        out["run_id"] = rm.run_id
        out["tags"] = rm.tags
        out["descr"] = rm.description
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
