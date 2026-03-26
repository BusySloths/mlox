# Services Catalog

A full reference of all MLOps services supported by MLOX, organized by category.

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

---

## ML Platforms

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **MLflow** | 2.22.0, 3.8.1 | Industry-standard ML experiment tracking, model registry, and lifecycle management. | ✅ Stable |
| **Apache Airflow** | 2.9.2, 3.1.3 | Workflow orchestration platform for scheduling and monitoring ML pipelines. | ✅ Stable |

---

## Model Serving

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **MLflow MLServer** | 2.22.0, 3.8.1, 3.8.1 (k3s) | Production-ready async REST/gRPC APIs for ML models, backed by MLflow model registry. | ✅ Stable |

---

## LLMs & Inference

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **LiteLLM + Ollama** | 1.77.7 | Unified LLM proxy supporting 100+ providers (OpenAI, Anthropic, local Ollama models, and more). | ✅ Stable |

---

## Vector & Feature Stores

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **Milvus** | 2.5 | Open-source vector database designed for scalable similarity search and embeddings. | ✅ Stable |
| **Feast Feature Store** | 0.54.0 | Open-source feature store for managing and serving ML features across training and serving. | ✅ Stable |

---

## Data & Streaming

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **PostgreSQL** | 16 | Powerful, open-source object-relational database system. | ✅ Stable |
| **Redis** | 8 | Open-source, in-memory data structure store, used as cache, database, and message broker. | ✅ Stable |
| **MinIO** | RELEASE.2025-07-23 | High-performance, S3-compatible object store for ML artifacts and datasets. | ✅ Stable |
| **Apache Kafka** | 3.7.0, 4.1.0 | Distributed event streaming platform for high-performance data pipelines. | ✅ Stable |

---

## Observability

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **InfluxDB** | 1.11.8 | Time-series database designed for high-performance metrics storage and retrieval. | ✅ Stable |
| **OpenTelemetry Collector** | 0.127.0, 0.146.1 | Vendor-agnostic telemetry pipeline for collecting metrics, logs, and traces. | ✅ Stable |

---

## Secrets & Access

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **OpenBao** | 2.4.1 | Vault-compatible secret management server (open-source fork of HashiCorp Vault). | ✅ Stable |
| **TinySecretManager (TSM)** | 0.1-beta | Lightweight, file-based secret management for local or low-complexity deployments. | ✅ Stable |
| **Private Docker Registry** | 3 | Secure, private Docker distribution registry with TLS and htpasswd authentication. | ✅ Stable |

---

## Kubernetes Add-ons

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **Kubernetes Dashboard** | 7.13.0 | Official web-based UI for managing Kubernetes clusters. | 🔄 Experimental |
| **Headlamp Dashboard** | latest | Modern, extensible web UI for managing Kubernetes clusters. | 🔄 Experimental |
| **KubeApps** | latest | Web-based UI for managing Helm-based Kubernetes applications. | 🔄 Experimental |

---

## Cloud Integrations

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **GCP BigQuery** | 0.1.0 | Fully managed, serverless data warehouse for scalable analytics. | 🔄 Experimental |
| **GCP Cloud Storage** | 0.1.0 | Scalable object storage for ML datasets and artifacts on GCP. | 🔄 Experimental |
| **GCP Sheets** | 0.1.0 | Google Spreadsheets integration for lightweight data ingestion and reporting. | 🔄 Experimental |
| **GCP Secret Manager** | 0.1.0 | Secure, scalable secret management on Google Cloud Platform. | 🔄 Experimental |

---

## Source Control

| Service | Version(s) | Description | Status |
|---------|-----------|-------------|--------|
| **GitHub Repository** | 0.1-beta | Clone and pull GitHub repositories onto your managed servers. | ✅ Stable |

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ Stable | Production-ready, actively maintained |
| 🔄 Experimental | Functional but under active development; APIs may change |

---

## See Also

- [Home](Home) — Project overview
- [Plugin Guide](Plugin-Guide) — How to add external service plugins
- [Architecture](Architecture) — Codebase walkthrough
