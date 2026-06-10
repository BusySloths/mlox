<p align="center">
  <a href="https://github.com/BusySloths/mlox">
    <img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/mlox_sloth_logo.png?raw=true" alt="MLOX Logo" width="400px"/>
  </a>
</p>

<p align="center">
  <strong>Deploy and manage ML/AI infrastructure on your own servers. Slothfully simple.</strong>
</p>

<p align="center">
  Servers, Docker, Kubernetes, databases, workflows, model serving, data services, tracking, and monitoring, with your product at the center. Managed in one place and connected by design.
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

ML/AI infrastructure is fragmented. Setup is painful, managed platforms are expensive, and vendor lock-in limits your choices.

MLOX brings the infrastructure around your product into one connected system. It manages servers, sets up Docker and Kubernetes clusters, deploys open-source services, stores secrets, and wires dependencies across databases, workflows, experiment tracking, model serving, data services, and monitoring.

Use the Web UI, TUI, or CLI to operate the same inspectable, configuration-driven core. MLOX is built for solopreneurs, startups, and small teams that want to focus on their product instead of assembling and maintaining infrastructure.

It's for engineers who prefer thoughtful systems over chaos. Backed by open source. Powered by sloths.

> **[State of the Union (Sept 2025)](https://drive.google.com/file/d/1Y368yXcaQt1dJ6riOCzI7-pSQBnJjyEP/view?usp=sharing)** — a short slide overview of what MLOX is, what problem it solves, and where it's heading.

---

## Current Status

Native, Docker, and Kubernetes execution, connector integrations, and the major services are functional. The project has been accepted at **CAIN 2026**.

We welcome contributors, users, and honest feedback. If you hit something broken, please [open an issue](https://github.com/BusySloths/mlox/issues/new/choose) or reach out at `contact@mlox.org`.

---

## What Can You Do with MLOX?

| Area | What's included |
|------|----------------|
| **Infrastructure** | Add, remove, and tag servers; use Native, Docker, or Kubernetes execution; create single- or multi-node clusters |
| **Services** | Deploy, manage, and remove services; centralize secrets; connect service dependencies |
| **Connectors** | Integrate externally hosted services such as BigQuery, Cloud Storage, Sheets, and GCP Secret Manager |
| **Applications** | Import repositories and deploy your product alongside its supporting services |
| **Code** | `busysloths-mlox` PyPI package with client integrations, SDK helpers, and example snippets |
| **Lifecycle Management** | Migrate, upgrade, export, and decommission services *(planned)* |

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

## Architecture in 30 Seconds

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
│   ├── application/    # Shared use cases and infrastructure operations
│   ├── cli/            # Typer CLI package (root app + command modules)
│   ├── execution/      # Backend and system execution helpers
│   ├── migrations/     # Persisted project format migrations
│   ├── servers/        # Local, connector, and Ubuntu compute with Native, Docker, or Kubernetes
│   ├── services/       # Deployable ML/AI services and integrations
│   ├── tui/            # Textual terminal UI + TUI-specific UI handlers
│   ├── ui/             # Frontend UI handler registry
│   ├── view/           # Streamlit web UI + Streamlit-specific UI handlers
│   ├── assets/         # Runtime templates and packaged assets
│   ├── resources/      # Images and other static resources
│   ├── session.py      # Runtime state & persistence
│   ├── infra.py        # Service/server graph
│   ├── config.py       # YAML loading + plugin discovery + UI handler lookup
│   └── executors.py    # Remote task executor layer used by services/servers
├── tests/
│   ├── unit/           # Fast tests, no external deps
│   └── integration/    # Multipass VM tests
├── examples/           # OTel, MLflow tracking, DAG templates
├── docs/               # Architecture, installation, contribution guides
├── wiki/               # GitHub Wiki source pages
├── scripts/            # Development and maintenance utilities
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
| [Plugin Guide](docs/PLUGIN_CONFIGS.md) | External service and server config plugins |
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
