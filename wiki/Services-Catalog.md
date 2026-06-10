# Services Catalog

A reference to the ML/AI infrastructure services and integrations currently included with MLOX.

---

## Contents

1. [ML Platforms](#ml-platforms)
2. [Model Serving](#model-serving)
3. [LLMs & Inference](#llms--inference)
4. [Vector & Feature Stores](#vector--feature-stores)
5. [Data & Streaming](#data--streaming)
6. [Observability](#observability)
7. [Secrets & Access](#secrets--access)
8. [Kubernetes Add-ons](#kubernetes-add-ons)
9. [Cloud Integrations](#cloud-integrations)
10. [Source Control](#source-control)
11. [Applications](#applications)

---

## ML Platforms

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **MLflow** | 2.22.0, 3.8.1 | ML experiment tracking, model registry, and lifecycle management. | Functional |
| **Apache Airflow** | 2.9.2, 3.1.3 | Workflow orchestration platform for scheduling and monitoring ML pipelines. | Functional |

---

## Model Serving

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **MLflow MLServer** | 2.22.0, 3.8.1, 3.8.1 (k3s) | REST/gRPC model serving backed by an MLflow model registry. | Functional |
| **MLflow Gateway** | 3.8.1 | Lightweight authenticated HTTP gateway that loads and caches models from an MLflow registry. | Functional |

---

## LLMs & Inference

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **LiteLLM + Ollama** | 1.77.7 | Unified LLM proxy supporting hosted providers and local Ollama models. | Functional |
| **Ollama** | 0.23.3 | Standalone local LLM API with HTTPS and BasicAuth provided by Traefik. | Functional |

---

## Vector & Feature Stores

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **Milvus** | 2.5 | Open-source vector database designed for scalable similarity search and embeddings. | Functional |
| **Feast Feature Store** | 0.54.0 | Open-source feature store for managing and serving ML features across training and serving. | Functional |

---

## Data & Streaming

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **PostgreSQL** | 16 | Open-source object-relational database system. | Functional |
| **Redis** | 8 | In-memory data store used as a cache, database, and message broker. | Functional |
| **MinIO** | RELEASE.2025-07-23 | S3-compatible object store for ML artifacts and datasets. | Functional |
| **Apache Kafka** | 3.7.0, 4.1.0 | Distributed event streaming platform for data pipelines. | Functional |

---

## Observability

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **InfluxDB** | 1.11.8 | Time-series database for metrics storage and retrieval. | Functional |
| **OpenTelemetry Collector** | 0.127.0, 0.146.1 | Vendor-agnostic telemetry pipeline for collecting metrics, logs, and traces. | Functional |

---

## Secrets & Access

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **OpenBao** | 2.4.1 | Vault-compatible secret management server. | Functional |
| **TinySecretManager (TSM)** | 0.1-beta | Lightweight, file-based secret management for local or low-complexity deployments. | Beta |
| **Registry 3** | 3 | Private Docker distribution registry with TLS and htpasswd authentication. | Functional |

---

## Kubernetes Add-ons

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **Kubernetes Dashboard** | 7.13.0 | Web-based UI for managing Kubernetes clusters. | Experimental |
| **Headlamp Dashboard** | latest | Extensible web UI for managing Kubernetes clusters. | Experimental |
| **KubeApps** | latest | Web-based UI for managing Helm-based Kubernetes applications. | Experimental |

---

## Cloud Integrations

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **GCP BigQuery** | 0.1.0 | Connector for the managed BigQuery data warehouse. | Functional |
| **GCP Cloud Storage** | 0.1.0 | Connector for storing ML datasets and artifacts in Cloud Storage. | Functional |
| **GCP Sheets** | 0.1.0 | Google Sheets connector for lightweight data ingestion and reporting. | Functional |
| **GCP Secret Manager** | 0.1.0 | Connector for secret management on Google Cloud Platform. | Functional |

---

## Source Control

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **GitHub Repository** | 0.1-beta | Clone and pull GitHub repositories onto managed servers. | Beta |

---

## Applications

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **Repository Docker Deploy** | 0.1-beta | Deploy a Docker Compose application from a repository already managed by MLOX. | Beta |

---

## Legend

| Status | Meaning |
|--------|---------|
| Functional | Implemented and available in the current release |
| Beta | Usable, but the workflow or interface is still evolving |
| Experimental | Early implementation with a higher likelihood of change |

---

## See Also

- [Home](Home) — Project overview
- [Plugin Guide](Plugin-Guide) — How to add external service plugins
- [Architecture](Architecture) — Codebase walkthrough
