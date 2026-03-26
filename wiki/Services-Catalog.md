# Services Catalog

A complete reference of all MLOps services supported by MLOX.

---

## Contents

1. [Overview](#overview)
2. [Catalog by Category](#catalog-by-category)
3. [What You Can Do with Services](#what-you-can-do-with-services)
4. [Service Authoring Conventions](#service-authoring-conventions)

---

## Overview

MLOX deploys services as configuration-driven units. Each service:

- Has a **YAML config** describing its identity, ports, groups, and build class
- Supports one or more **backends** (Native, Docker, Kubernetes)
- Exposes a `get_secret()` method for access credentials
- May provide a **`client.py`** helper for Python integration

---

## Catalog by Category

| Category | Services | Status |
|----------|----------|--------|
| **ML Platforms** | MLflow 2.x, MLflow 3.x, Airflow 2.x, Airflow 3.x | ✅ Stable |
| **Model Serving** | MLflow MLServer | ✅ Stable |
| **LLMs & Inference** | LiteLLM | ✅ Stable |
| **Vector & Feature Stores** | Milvus, Feast | ✅ Stable |
| **Data & Streaming** | PostgreSQL, Redis, MinIO, Kafka | ✅ Stable |
| **Observability** | InfluxDB, OpenTelemetry | ✅ Stable |
| **Secrets & Access** | OpenBao, Tiny Secret Manager, Docker Registry | ✅ Stable |
| **Kubernetes Add-ons** | K8s Dashboard, Headlamp, KubeApps | 🔄 Experimental |
| **Cloud Integrations** | GCP (BigQuery, Cloud Storage, Sheets, Secret Manager) | 🔄 Experimental |
| **Source Control** | GitHub repository import | ✅ Stable |

---

## What You Can Do with Services

| Action | Description |
|--------|-------------|
| **Deploy** | Install and start a service on a target server |
| **Update** | Apply configuration changes or upgrade versions |
| **Remove** | Cleanly uninstall a service and free resources |
| **Secrets** | Centralized secret storage and retrieval per service |
| **Dependencies** | Wire services together (e.g., MLflow → PostgreSQL) |

---

## Backend Support

All stable services support the three MLOX backends:

| Backend | Description |
|---------|-------------|
| **Native** | Direct installation on Ubuntu servers via SSH |
| **Docker** | Container-based deployment with Docker Compose |
| **Kubernetes** | Manifest-driven deployment on Kubernetes clusters |

---

## Service Authoring Conventions

Each service lives under `mlox/services/<service-name>/` and follows these conventions:

- **YAML config** (`mlox.<service-id>.yaml`) — defines service identity, ports, groups, requirements, and build class
- **Backend-specific classes** — one implementation class per supported backend (native, docker, k8s)
- **Deployment files** — e.g., Docker Compose templates bundled with the service
- **`client.py`** _(optional)_ — Python helper so users can consume the service from code
- **`get_secret()`** — every service exposes this method, returning access credentials (user, password, endpoint, etc.)

### Service Dependencies

Services can declare dependencies on other services:

- Dependency UUIDs are stored on service objects
- Dependent services are resolved via the `get_dependent_service` helper pattern

For more details on the configuration schema, see the [Plugin Guide](Plugin-Guide) or the [Architecture](Architecture) page.

---

## See Also

- [Home](Home) — Project overview and navigation
- [Architecture](Architecture) — Codebase walkthrough
- [Plugin Guide](Plugin-Guide) — Adding external service plugins
- [API Docs](https://busysloths.github.io/mlox/mlox.html) — Full API reference
