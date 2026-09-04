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
</p>

---

## What is MLOX?

ML/AI infrastructure is fragmented. Setup is painful, managed platforms are expensive, and vendor lock-in limits your choices.

MLOX brings the infrastructure around your product into one connected system. It manages servers, sets up Docker and Kubernetes clusters, deploys open-source services, stores secrets, and wires dependencies across databases, workflows, experiment tracking, model serving, data services, and monitoring.

Use the CLI or TUI to operate the same inspectable, configuration-driven core. MLOX is built for solopreneurs, startups, and small teams that want to focus on their product instead of assembling and maintaining infrastructure.

It's for engineers who prefer thoughtful systems over chaos. Backed by open source. Powered by sloths.

> **Status, roadmap, and decisions** — see [docs/DOCTRINE.md](docs/DOCTRINE.md), the single point of truth.

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

MLOX bundles a growing set of self-hosted services and connectors (MLflow,
Airflow, Milvus, Feast, Kafka, LiteLLM, OpenBao, GCP, and more). The exhaustive,
authoritative list — generated directly from the YAML plugin configs — lives in
[**docs/SERVICES_CATALOG.md**](docs/SERVICES_CATALOG.md). Per-component maturity
status is tracked in [docs/DOCTRINE.md](docs/DOCTRINE.md).

---

## Architecture in 30 Seconds

```text
CLI     TUI
  \      |
   +-----+
          |
          v
      `ProjectWorkspace`
          |
          v
   internal state + repository
          |
          v
 encrypted `project.mlox` (SQLCipher)
 metadata + data-source pointer + infrastructure + secrets
          |
          +-- active source: `self` today
          +-- PostgreSQL-ready repository boundary later
```

`ProjectWorkspace` is the single public runtime API. It loads and atomically
persists internal workspace state containing metadata and `Infrastructure`;
the single selected secret manager is available through `workspace.secrets`.
Encrypted project storage is selected initially, with no silent fallback when an
external provider is unavailable. The project
also records its active data source (`sqlcipher/self` initially), leaving a clean
migration path to PostgreSQL. CLI commands open a workspace per invocation,
while the TUI retains one workspace in runtime state. (The Streamlit web UI is
deprecated — see [docs/DOCTRINE.md](docs/DOCTRINE.md).)

Service and server definitions remain inspectable and configuration-driven, while execution is handled consistently across Native, Docker, Kubernetes, and connector backends.

For deeper reading:

- [Architecture Guide](docs/ARCHITECTURE.md) — codebase walkthrough

---

## Quickstart

```bash
# 1. Install Task (https://taskfile.dev/installation/)

# 2. Clone
git clone https://github.com/BusySloths/mlox.git && cd mlox

# 3. Set up environment (creates conda env 'mlox-dev' with Python 3.12.5)
task first:steps

# 4. Launch the CLI
task ui:cli CLI_ARGS="--help"

# 5. Or launch the TUI
task ui:textual:terminal
```

See [Installation Guide](docs/INSTALLATION.md) for a fuller walkthrough including Docker and Kubernetes setup. See [Encrypted Project Files](docs/PROJECT_FILES.md) for creation, storage, backup, and legacy migration details.

---

## Project Structure

```
mlox/
├── mlox/
│   ├── application/    # Stateful application API and shared use cases
│   ├── cli/            # Typer CLI package (root app + command modules)
│   ├── execution/      # Backend and system execution helpers
│   ├── project/        # Aggregate, SQLCipher repository, and secret adapter
│   ├── servers/        # Local, connector, and Ubuntu compute with Native, Docker, or Kubernetes
│   ├── services/       # Deployable ML/AI services and integrations
│   ├── tui/            # Textual terminal UI + TUI-specific UI handlers
│   ├── ui/             # Frontend UI handler registry
│   ├── assets/         # Runtime templates and packaged assets
│   ├── resources/      # Images and other static resources
│   ├── view/           # Streamlit web UI — deprecated (moving to plugin repo)
│   ├── infra.py        # Service/server graph
│   ├── config.py       # YAML loading + plugin discovery + UI handler lookup
│   └── executors.py    # Remote task executor layer used by services/servers
├── tests/
│   ├── unit/           # Fast tests, no external deps
│   └── integration/    # Multipass VM tests, including Kubernetes/k3s tests
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
task tests:integration:k8s      # Kubernetes integration tests (requires Multipass/k3s)
```

### Ways to Contribute

- [Bug reports](https://github.com/BusySloths/mlox/issues/new/choose)
- [Documentation improvements](https://github.com/BusySloths/mlox/issues/new/choose)
- [Feature requests](https://github.com/BusySloths/mlox/issues/new/choose)
- [New service implementations](docs/ARCHITECTURE.md)
- [Examples and tutorials](examples/)

See [CONTRIBUTING.md](CONTRIBUTING.md) for the issue, milestone, and PR workflow.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Doctrine](docs/DOCTRINE.md) | Status, roadmap, and binding decisions (single point of truth) |
| [Services Catalog](docs/SERVICES_CATALOG.md) | Generated service/server catalog |
| [Architecture](docs/ARCHITECTURE.md) | Codebase walkthrough |
| [Installation Guide](docs/INSTALLATION.md) | Setup from scratch |
| [Project Files](docs/PROJECT_FILES.md) | Encrypted project files, backup, migration |
| [Contributing Guide](CONTRIBUTING.md) | How to contribute |
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
