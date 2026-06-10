<p align="center">
  <img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/mlox_sloth_logo.png?raw=true" alt="MLOX Logo" width="300px"/>
</p>

# Welcome to the MLOX Wiki

> **Sovereign AI Infrastructure. Open by Design. Slothfully Simple.**

MLOX is a configuration-driven control plane for deploying production-grade MLOps on your own servers — without cloud lock-in. You define your stack in YAML, MLOX handles the rest: deploying services, managing secrets, and wiring dependencies across backends.

---

## Why MLOX?

Cloud MLOps costs thousands per month. Setup is painful. Vendor lock-in is a trap.

MLOX gives you a calm, reproducible way to run production-grade ML infrastructure on your own servers or hybrid cloud. Three interfaces (Web UI, TUI, CLI) share one inspectable, config-driven core, while frontend-specific UI handlers are registered separately. It's for engineers who prefer thoughtful systems over chaos.

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
| **Infrastructure** | Add/remove/tag servers; choose Native, Docker, or Kubernetes runtime; spin up single- or multi-node clusters |
| **Services** | Deploy, update, and remove services; centralized secrets; dependency wiring between services |
| **Code** | `busysloths-mlox` PyPI package with client integrations, SDK helpers, and example snippets |
| **Lifecycle Management** | Migrate, upgrade, export, and decommission services _(planned)_ |

---

## Services Catalog

| Category | Services | Status |
|----------|----------|--------|
| ML Platforms | MLflow 2.x, MLflow 3.x, Airflow 2.x, Airflow 3.x | ✅ Stable |
| Model Serving | MLflow MLServer | ✅ Stable |
| LLMs & Inference | LiteLLM, Ollama | ✅ Stable |
| Vector & Feature Stores | Milvus, Feast | ✅ Stable |
| Data & Streaming | PostgreSQL, Redis, MinIO, Kafka | ✅ Stable |
| Observability | InfluxDB, OpenTelemetry | ✅ Stable |
| Secrets & Access | OpenBao, Tiny Secret Manager, Docker Registry | ✅ Stable |
| Kubernetes Add-ons | K8s Dashboard, Headlamp, KubeApps | 🔄 Experimental |
| Cloud Integrations | GCP (BigQuery, Cloud Storage, Sheets, Secret Manager) | ✅ Stable |
| Source Control | GitHub repository import | ✅ Stable |

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

`MloxSession` is the runtime center: it always carries project metadata, an encrypted key-value secret manager, and the current `Infrastructure`. The important shared application layer is `mlox/application/use_cases/*`; CLI already routes through it, and TUI/Web/future UIs should do the same. `Infrastructure` models topology through bundles, where each bundle groups one compute/server with its services. Anything executed on a compute goes through the execution layer, while compute capabilities already exist (`git`, `docker`, `kubernetes`, ...) and service capabilities are an emerging architectural direction.

YAML stays focused on deployable configs and Python build classes. Streamlit and TUI-specific setup/settings handlers live in the frontend packages and are resolved through `mlox/ui/registry.py`, which keeps UI code out of the service/server config layer and prepares a future plugin extension point.

→ Read the full [Architecture](Architecture) page for a deep dive.

---

## Quickstart

### Try via PyPI (no clone needed)

```bash
# 1. Create a Python environment (Python 3.11 or 3.12)
conda create -n mlox python=3.12 -y
conda activate mlox

# 2. Install MLOX
pip install "busysloths-mlox[all]"

# 3. Launch the web UI
mlox ui
```

### Develop from source

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

MLOX is in **active alpha development (v0.x)**. Core infrastructure, all three backends (Native, Docker, Kubernetes), and the major services are functional. The project has been accepted at **CAIN 2026**.

We welcome contributors, early adopters, and honest feedback.

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
