<p align="center">
  <img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/mlox_sloth_logo.png?raw=true" alt="MLOX Logo" width="300px"/>
</p>

# Welcome to the MLOX Wiki

> **Deploy and manage ML/AI infrastructure on your own servers. Slothfully simple.**

Servers, Docker, Kubernetes, databases, workflows, model serving, data services, tracking, and monitoring, with your product at the center. Managed in one place and connected by design.

---

## Why MLOX?

ML/AI infrastructure is fragmented. Setup is painful, managed platforms are expensive, and vendor lock-in limits your choices.

MLOX brings the infrastructure around your product into one connected system. It manages servers, sets up Docker and Kubernetes clusters, deploys open-source services, stores secrets, and wires dependencies across databases, workflows, experiment tracking, model serving, data services, and monitoring.

Use the Web UI, TUI, or CLI to operate the same inspectable, configuration-driven core. MLOX is built for solopreneurs, startups, and small teams that want to focus on their product instead of assembling and maintaining infrastructure.

It's for engineers who prefer thoughtful systems over chaos. Backed by open source. Powered by sloths.

---

## Quick Navigation

| Page | Description |
|------|-------------|
| [Architecture](Architecture) | Codebase walkthrough for human contributors |
| [Installation](Installation) | Setup from scratch (local, Docker, Kubernetes) |
| [Contributing](Contributing) | How to contribute to MLOX |
| [Troubleshooting](Troubleshooting) | Known setup and runtime issues with fixes and workarounds |
| [Services Catalog](Services-Catalog) | All supported MLOps services |
| [Plugin Guide](Plugin-Guide) | External service and server config plugins |

---

## What Can You Do with MLOX?

| Area | What's included |
|------|----------------|
| **Infrastructure** | Add, remove, and tag servers; use Native, Docker, or Kubernetes execution; spin up single- or multi-node clusters |
| **Connectors** | Integrate externally hosted services such as BigQuery, Cloud Storage, Sheets, and GCP Secret Manager |
| **Services** | Deploy, manage, and remove services; centralize secrets; wire dependencies between services |
| **Applications** | Import repositories and deploy your product alongside its supporting services |
| **Code** | `busysloths-mlox` PyPI package with client integrations, SDK helpers, and example snippets |
| **Lifecycle Management** | Migrate, upgrade, export, and decommission services _(planned)_ |

---

## Services Catalog

| Category | Services | Status |
|----------|----------|--------|
| ML Platforms | MLflow 2.x, MLflow 3.x, Airflow 2.x, Airflow 3.x | Functional |
| Model Serving | MLflow MLServer, MLflow Gateway | Functional |
| LLMs & Inference | LiteLLM, Ollama | Functional |
| Vector & Feature Stores | Milvus, Feast | Functional |
| Data & Streaming | PostgreSQL, Redis, MinIO, Kafka | Functional |
| Observability | InfluxDB, OpenTelemetry | Functional |
| Secrets & Access | OpenBao, Tiny Secret Manager, Registry 3 | Functional / Beta |
| Kubernetes Add-ons | Kubernetes Dashboard, Headlamp, KubeApps | Experimental |
| Cloud Integrations | GCP (BigQuery, Cloud Storage, Sheets, Secret Manager) | Functional |
| Source Control | GitHub repository import | Beta |
| Applications | Repository Docker Deploy | Beta |

---

## Architecture at a Glance

```text
CLI     TUI     Streamlit Web UI     Other UIs
  \      |             |                /
   \     |             |               /
    +----+-------------+--------------+
                    |
                    v
      `mlox/application/use_cases/*`
         shared session-based logic
                    |
                    v
              `MloxSession`
   project + encrypted secret manager + infrastructure
             /                               \
            v                                 v
 secret-manager backend                `Infrastructure`
 (InMemory/TinySM/OpenBao/GCP)      topology for one project
                                            |
                                            v
                           `Bundle` = compute/server + services[*]
                                      |
                                      v
                    execution via `mlox/executors.py` + `mlox/execution/*`
```

`MloxSession` holds the current project, its encrypted secret manager, and its infrastructure. Infrastructure is organized into bundles that pair a compute/server with its deployed services, keeping the product and its supporting stack connected in one topology. The CLI, TUI, and Web UI operate on this shared model through common application use cases.

Service and server definitions remain inspectable and configuration-driven, while execution is handled consistently across Native, Docker, Kubernetes, and connector backends.

→ Read the full [Architecture](Architecture) page for a deep dive.

---

## Quickstart

```bash
# 1. Install Task (https://taskfile.dev/installation/)

# 2. Clone
git clone https://github.com/BusySloths/mlox.git && cd mlox

# 3. Set up environment (creates conda env 'mlox-dev' with Python 3.12.5)
task first:steps

# 4. Launch the Web UI
task ui:streamlit

# 5. Or try the CLI
task ui:cli CLI_ARGS="--help"
```

See the [Installation](Installation) wiki page or [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) for Docker and Kubernetes setup.

---

## Project Status

Native, Docker, and Kubernetes execution, connector integrations, and the major services are functional. The project has been accepted at **CAIN 2026**.

We welcome contributors, users, and honest feedback.

- 🐛 [Open an issue](https://github.com/BusySloths/mlox/issues/new/choose)
- 💬 [Start a discussion](https://github.com/BusySloths/mlox/discussions)
- 📧 [contact@mlox.org](mailto:contact@mlox.org)

---

## Documentation Index

| Document | Link |
|----------|------|
| Architecture (humans) | [Architecture](Architecture) wiki page · [`docs/ARCHITECTURE_HUMANS.md`](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE_HUMANS.md) |
| Architecture (agents) | [`docs/ARCHITECTURE_AGENTS.md`](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE_AGENTS.md) |
| Installation Guide | [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) |
| Contributing Guide | [`CONTRIBUTING.md`](https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md) |
| Workflow Quick Reference | [`docs/WORKFLOW_QUICK_REFERENCE.md`](https://github.com/BusySloths/mlox/blob/main/docs/WORKFLOW_QUICK_REFERENCE.md) |
| Plugin Guide | [`docs/PLUGIN_CONFIGS.md`](https://github.com/BusySloths/mlox/blob/main/docs/PLUGIN_CONFIGS.md) |
| API Docs | [busysloths.github.io/mlox/docs](https://busysloths.github.io/mlox/docs/mlox.html) |
| Website | [mlox.org](https://mlox.org) |

---

## License

MLOX is open-source under the [MIT License](https://github.com/BusySloths/mlox/blob/main/LICENSE).

---

_Powered by sloths. 🦥_
