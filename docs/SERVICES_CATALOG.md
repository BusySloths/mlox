# Services Catalog

> AUTO-GENERATED. Do not edit by hand. Run `python scripts/generate_service_catalog.py` to regenerate from the YAML configs. Any hand-written catalog content is a drift bug.

The authoritative, exhaustive list of services and servers bundled with MLOX. Generated from the YAML plugin configs; the single source of truth is those configs, not this page.

**36 service configs, 9 server configs.**

---

## Contents

1. [Services](#services)
2. [Servers](#servers)

---

## Services

| Service | Version | Backends | Description |
|---------|---------|----------|-------------|
| **Airflow** | 2.9.2 | docker | Apache Airflow is a workflow orchestrator used to schedule and monitor machine learning pipelines. |
| **Airflow** | 3.1.3 | docker | Apache Airflow is a workflow orchestrator used to schedule and monitor machine learning pipelines. |
| **Apache Kafka** | 4.1.0 | docker | Apache Kafka is a distributed event streaming platform for high-performance data pipelines. |
| **Bitnami Kafka** | 3.7.0 | docker | Apache Kafka is a distributed event streaming platform for high-performance data pipelines. |
| **Developers Terminal Dream** | 0.1-beta | docker, k3s_agent, kubernetes, kubernetes_agent, native | Install a terminal-first developer workstation on MLOX backends. |
| **Feast Feature Store** | 0.54.0 | docker | Feast is an open-source feature store for managing and serving machine learning features. |
| **GCP BigQuery** | 0.1.0 | connector | GCP BigQuery is a fully managed, serverless data warehouse that enables scalable analysis over petabytes of data. |
| **GCP Secret Manager** | 0.1.0 | connector | GCP Secret Manager is a secure and scalable service for managing secrets in Google Cloud Platform. |
| **GCP Sheets** | 0.1.0 | connector | Google Spreadsheets is a secure and scalable service for managing sheets in Google Cloud Platform. |
| **GCP Storage** | 0.1.0 | connector | GCP Storage is a secure and scalable service for managing storage in Google Cloud Platform. |
| **Github Repository** | 0.1-beta | docker, kubernetes, native | Clone and pull Github Repositories on your servers. |
| **Headlamp Dashboard** | newest | kubernetes | Headlamp is a web-based UI for managing Kubernetes clusters. |
| **InfluxDB** | 1.11.8 | docker | InfluxDB is a time-series database designed for high-performance data storage and retrieval. |
| **KubeApps** | 3.0.0 | kubernetes | KubeApps is a web-based UI for managing Kubernetes applications. |
| **Kubeflow** | 1.10.1 | kubernetes | A Kubernetes-native platform for machine learning workflows. |
| **Kubernetes Dashboard** | 7.13.0 | kubernetes | Kubernetes Dashboard is a web-based UI for managing Kubernetes clusters. |
| **LiteLLM + Ollama** | 1.77.7 (stable) | docker | LiteLLM is an open-source library that simplifies the integration of large language models (LLMs) into applications. |
| **Milvus** | 2.5 | docker | Milvus is an open-source vector database designed for scalable similarity search. |
| **MinIO** | RELEASE.2025-07-23T15-54-02Z-cpuv1 | docker | MinIO is a high-performance, S3 compatible object store. |
| **MLFlow** | 2.22.0 | docker | MLFlow is an open-source platform for managing the machine learning lifecycle, including experimentation, reproducibility, and deployment. |
| **MLFlow** | 3.8.1 | docker | MLFlow is an open-source platform for managing the machine learning lifecycle, including experimentation, reproducibility, and deployment. |
| **MLFlow Gateway** | 3.8.1 | kubernetes | Lightweight multi-model HTTP gateway for MLflow on Kubernetes. |
| **MLFlow Gateway** | 3.8.1 | docker | Lightweight multi-model HTTP gateway for MLflow registry models. |
| **MLFlow Gateway (managed TLS)** | 3.8.1 | kubernetes | MLflow model gateway on k3s using secret-manager-backed TLS. |
| **MLFlow-MLServer** | 2.22.0 | docker | MLServer is an open-source Python library for building production-ready asynchronous APIs for machine learning models. |
| **MLFlow-MLServer** | 3.8.1 | kubernetes | Deploy an MLflow registry model with MLServer on Kubernetes (k3s). |
| **MLFlow-MLServer** | 3.8.1 | docker | MLServer is an open-source Python library for building production-ready asynchronous APIs for machine learning models. |
| **Ollama** | 0.23.3 | docker | Standalone Ollama service with HTTPS and BasicAuth via Traefik. |
| **OpenBao** | 2.5.4 | docker | OpenBao provides a Vault-compatible secret management server. |
| **OpenTelemetry Collector** | 0.127.0 | docker | OpenTelemetry Collector is a service for collecting and exporting telemetry data. |
| **OpenTelemetry Collector** | 0.146.1 | docker | OpenTelemetry Collector is a service for collecting and exporting telemetry data. |
| **Postgres** | 16-bullseye | docker | Postgres is a powerful, open-source object-relational database system. |
| **Private Registry** | 3 | docker | Secure, private Docker distribution registry with TLS and htpasswd auth. |
| **Redis** | 8-bookworm | docker | Redis is an open-source, in-memory data structure store. |
| **Repository Docker Deploy** | 0.1-beta | docker | Deploy a docker compose file from an existing repository service. |
| **TinySecretManager (TSM)** | 0.1-beta | docker, kubernetes, native | TinySecretManager is a lightweight, file-based secret management service. |

---

## Servers

| Service | Version | Backends | Description |
|---------|---------|----------|-------------|
| **Connector Backend** | 0.1.0 | connector | Virtual backend for externally hosted connector services. |
| **Localhost** | 0.1.0 | local | Localhost server for development and testing. |
| **Ubuntu (Docker)** | 24.04 | docker | Ubuntu with Docker backend. |
| **Ubuntu (Kubernetes, K3S)** | 24.04 | kubernetes | Ubuntu with Kubernetes-K3S backend. |
| **Ubuntu (Native)** | 24.04 | native | Ubuntu with Native backend. |
| **Ubuntu (no setup)** | 24.04 | native | Ubuntu with pre-configured access. |
| **Ubuntu Multipass VM (Docker)** | 24.04 | docker | Ubuntu Multipass VM with Docker backend. |
| **Ubuntu Multipass VM (Kubernetes, K3S)** | 24.04 | kubernetes | Ubuntu Multipass VM with Kubernetes-K3S backend. |
| **Ubuntu Multipass VM (Native)** | 24.04 | native | Ubuntu Multipass VM with Native backend. |

---

## Status Legend

Maturity/status (Functional, Beta, Experimental) is not part of the YAML schema and is therefore NOT listed here. It is tracked in `docs/DOCTRINE.md` — the single point of truth for status.

