# mlox
MLOps-in-a-Box: A simple and cost-efficient way of running your OSS MLOps stack.

--------

Templates for building MLOps service infrastructure for on-prem/vps/GCP.

Consists of scripts that handle linux install, setup incl. ssl/tls, docker via a streamlit web ui:

    1. Airflow ETL package
    2. MLFlow
    3. MLServer/Flask/FastAPI
    4. OpenTelemetry + NewRelic Bindings

    1. Feast Feature Store
    2. Milvus VectorDB

    LLM package:
    1. LiteLLM + Ollama
    2. Open Web UI (LiteLLM + Ollama Bindings)
