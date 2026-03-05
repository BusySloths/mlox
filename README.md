<p align="center">
  <a href="https://github.com/BusySloths/mlox">
    <img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/mlox_sloth_logo.png?raw=true" alt="MLOX Logo" width="400px"/>
  </a>
</p>

<p align="center">
  <strong>Sovereign AI Infrastructure. Open by Design. Slothfully Simple.</strong>
</p>

<p align="center">
  A configuration-driven control plane for deploying production-grade MLOps on your own servers — without cloud lock-in.
</p>

<p align="center">
  <a href="https://qlty.sh/gh/BusySloths/projects/mlox" target="_blank"><img src="https://qlty.sh/gh/BusySloths/projects/mlox/maintainability.svg" alt="Maintainability" /></a>
  <a href="https://qlty.sh/gh/BusySloths/projects/mlox" target="_blank"><img src="https://qlty.sh/gh/BusySloths/projects/mlox/coverage.svg" alt="Code Coverage" /></a>
  <a href="https://github.com/BusySloths/mlox/issues" target="_blank"><img alt="GitHub Issues" src="https://img.shields.io/github/issues/busysloths/mlox"></a>
  <a href="https://github.com/BusySloths/mlox/discussions" target="_blank"><img alt="GitHub Discussions" src="https://img.shields.io/github/discussions/busysloths/mlox"></a>
  <a href="https://drive.google.com/file/d/1Y368yXcaQt1dJ6riOCzI7-pSQBnJjyEP/view?usp=sharing"><img src="https://img.shields.io/badge/Slides-State_of_the_Union-9cf" alt="Slides: State of the Union" /></a>
</p>

---

## What is MLOX?

Cloud MLOps costs thousands per month. Setup is painful. Vendor lock-in is a trap.

MLOX is a calm, reproducible way to run production-grade ML infrastructure on your own servers or hybrid cloud. You define your stack in YAML, MLOX handles the rest — deploying services, managing secrets, and wiring dependencies across backends. Three interfaces (Web UI, TUI, CLI) share one inspectable config-driven core.

It's for engineers who prefer thoughtful systems over chaos. Backed by open source. Powered by sloths.

> **[State of the Union (Sept 2025)](https://drive.google.com/file/d/1Y368yXcaQt1dJ6riOCzI7-pSQBnJjyEP/view?usp=sharing)** — a short slide overview of what MLOX is, what problem it solves, and where it's heading.

---

## Current Status

MLOX is in **active alpha development (v0.x)**. Core infrastructure, all three backends (Native, Docker, Kubernetes), and the major services are functional. The project has been accepted at **CAIN 2026**.

We welcome contributors, early adopters, and honest feedback. If you hit something broken, please [open an issue](https://github.com/BusySloths/mlox/issues/new/choose) or reach out at `contact@mlox.org`.

---

## What Can You Do with MLOX?

| Area | What's included |
|------|----------------|
| **Infrastructure** | Add/remove/tag servers; choose Native, Docker, or Kubernetes runtime; spin up single- or multi-node clusters |
| **Services** | Deploy, update, and remove services; centralized secrets; dependency wiring between services |
| **Code** | `busysloths-mlox` PyPI package with client integrations, SDK helpers, and example snippets |
| **Lifecycle Management** | Migrate, upgrade, export, and decommission services *(planned)* |

---

## Services Catalog

| Category | Services | Status |
|----------|----------|--------|
| ML Platforms | MLflow 2.x, MLflow 3.x, Airflow 2.x, Airflow 3.x | ✅ Stable |
| Model Serving | MLflow MLServer | ✅ Stable |
| LLMs & Inference | LiteLLM | ✅ Stable |
| Vector & Feature Stores | Milvus, Feast | ✅ Stable |
| Data & Streaming | PostgreSQL, Redis, MinIO, Kafka | ✅ Stable |
| Observability | InfluxDB, OpenTelemetry | ✅ Stable |
| Secrets & Access | OpenBao, Tiny Secret Manager, Docker Registry | ✅ Stable |
| Kubernetes Add-ons | K8s Dashboard, Headlamp, KubeApps | 🔄 Experimental |
| Cloud Integrations | GCP (BigQuery, Cloud Storage, Sheets, Secret Manager) | 🔄 Experimental |
| Source Control | GitHub repository import | ✅ Stable |

---

## Architecture in 30 Seconds

```
YAML Configs ──► config.py ──► MloxSession ──► Infrastructure
                                    │
                              ┌─────┼─────┐
                             CLI   TUI   Web UI
```

Three interfaces, one core. Session startup reads an encrypted project file, loads the secret manager, and reconstructs the infrastructure graph. All remote shell operations route through `UbuntuTaskExecutor` — nothing embeds raw subprocess logic in service code.

For deeper reading:

- [Architecture Guide (humans)](docs/ARCHITECTURE_HUMANS.md) — codebase walkthrough
- [Architecture Guide (agents)](docs/ARCHITECTURE_AGENTS.md) — high-risk areas and invariants

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

See [Installation Guide](docs/INSTALLATION.md) for a fuller walkthrough including Docker and Kubernetes setup.

---

## Project Structure

```
mlox/
├── mlox/
│   ├── services/       # 20+ deployable ML services (one directory each)
│   ├── servers/        # Native and Ubuntu/SSH backends
│   ├── cli.py          # Typer CLI entry point
│   ├── tui/            # Textual terminal UI
│   ├── view/           # Streamlit web UI
│   ├── session.py      # Runtime state & persistence
│   ├── infra.py        # Service/server graph
│   ├── config.py       # YAML loading + plugin entry-point discovery
│   └── executors.py    # All remote shell operations
├── tests/
│   ├── unit/           # Fast tests, no external deps
│   └── integration/    # Multipass VM tests
├── examples/           # OTel, MLflow tracking, DAG templates
├── docs/               # Architecture, installation, contribution guides
└── website/            # Astro landing page
```

---

## Contributing

### Sloth-Friendly Setup

```bash
# 1. Install Task (https://taskfile.dev/installation/)
# 2. Clone the repo
git clone https://github.com/BusySloths/mlox.git && cd mlox
# 3. Set up the dev environment
task first:steps
# 4. Install dev dependencies
pip install -e .[dev]
```

### Run Tests

```bash
task dev:lint                   # flake8
task tests:unit:run             # unit tests (fast, no external deps)
task tests:integration:run      # integration tests (requires Multipass VMs)
```

### Ways to Contribute

- [Bug reports](https://github.com/BusySloths/mlox/issues/new/choose)
- [Documentation improvements](https://github.com/BusySloths/mlox/issues/new/choose)
- [Feature requests](https://github.com/BusySloths/mlox/issues/new/choose)
- [New service implementations](docs/ARCHITECTURE_HUMANS.md)
- [Examples and tutorials](examples/)

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide and [docs/WORKFLOW_QUICK_REFERENCE.md](docs/WORKFLOW_QUICK_REFERENCE.md) for how we use GitHub Projects, Milestones, and Issues.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](docs/INSTALLATION.md) | Setup from scratch |
| [Architecture (humans)](docs/ARCHITECTURE_HUMANS.md) | Codebase walkthrough |
| [Architecture (agents)](docs/ARCHITECTURE_AGENTS.md) | High-risk areas and invariants |
| [Contributing Guide](CONTRIBUTING.md) | How to contribute |
| [Workflow Quick Reference](docs/WORKFLOW_QUICK_REFERENCE.md) | Labels, milestones, PRs |
| [Plugin Guide](docs/PLUGIN_CONFIGS.md) | External service plugins |
| [API Docs](https://busysloths.github.io/mlox/mlox.html) | Generated Python API reference |

---

## Sponsors

MLOX is proudly funded by:

<img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/BMFTR_logo.jpg?raw=true" alt="BMFTR" width="420px"/>

## Supporters

<p align="center">
  <img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/PrototypeFund_logo_dark.png?raw=true" alt="PrototypeFund" width="380px"/>
</p>

---

## License & Contact

MLOX is open-source, distributed under the [MIT License](LICENSE). Contributions are welcome and subject to the same terms.

We are looking for people invested in the problem we're solving. Say hello at `contact@mlox.org` or start a conversation in [GitHub Discussions](https://github.com/BusySloths/mlox/discussions).
