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

## See It In Action

<p align="center">
  <img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/tui-demo.gif?raw=true" alt="MLOX TUI demo — loading a project and browsing tabs" width="960px"/>
</p>

<p align="center">
  <img src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/tui-overview.png?raw=true" alt="MLOX TUI — infrastructure overview" width="960px"/>
</p>

---

## Status

MLOX is in active development and has been accepted at **CAIN 2026**. What is
stable, beta, or experimental, and where the project is heading, is tracked in
one place: the [component status and roadmap in docs/DOCTRINE.md](docs/DOCTRINE.md).

We welcome contributors, users, and honest feedback. If you hit something broken, please [open an issue](https://github.com/BusySloths/mlox/issues/new/choose) or reach out at `contact@mlox.org`.

---

## What Can You Do with MLOX?

| Area | What's included |
|------|----------------|
| **Infrastructure** | Add, remove, and tag servers; run work natively, in Docker, or on single- or multi-node Kubernetes |
| **Services** | Deploy, manage, and remove services; centralize secrets; connect service dependencies |
| **Connectors** | Integrate externally hosted services such as BigQuery, Cloud Storage, Sheets, and GCP Secret Manager |
| **Applications** | Import repositories and deploy your product alongside its supporting services |
| **Knowledge** | Keep notes, wiki pages, FAQs, todos, and markdown kanban boards inside the encrypted project |
| **Operations** | Observe workload runs, keep incident evidence, plan work, and consult advisory agent workspaces |
| **Code** | `busysloths-mlox` PyPI package: the `ProjectWorkspace` SDK plus per-service client helpers |

---

## Services Catalog

MLOX bundles a growing set of self-hosted services and connectors (MLflow,
Airflow, Milvus, Feast, Kafka, LiteLLM, OpenBao, GCP, and more). The exhaustive,
authoritative list — generated directly from the YAML plugin configs — lives in
[**docs/SERVICES_CATALOG.md**](docs/SERVICES_CATALOG.md). Per-component maturity
status is tracked in [docs/DOCTRINE.md](docs/DOCTRINE.md).
For MLflow setup, model serving, and focused integration tests, see the
[MLflow service guide](mlox/services/mlflow/README.md).

---

## Architecture in 30 Seconds

MLOX plays two roles. As a **platform**, the CLI and TUI manage your
infrastructure. As a **client package**, your own code consumes the services
MLOX deployed.

```text
 PLATFORM  (manage infrastructure)          CLIENT  (consume services)

     CLI           TUI                       your code, notebooks, jobs
      └─────┬───────┘                                   │
            ▼                                           │ token or keyfile
     ProjectWorkspace       public API,                 ▼
            │               one commit per change    secret manager
            ▼                                           │ endpoints + credentials
     application use cases                              ▼
            │                                     service client helpers
            ▼                                     (e.g. services/feast/client.py)
     WorkspaceState ◄──► SQLCipher repository ──► encrypted project.mlox
            │
            ▼
     Infrastructure: bundles of one server + its services
            │
            ▼
     executors + backend adapters ──► native · Docker · Kubernetes · connector
```

The model has three tiers:

1. **Servers** are the machines: Ubuntu hosts, your local machine, or a virtual
   "connector" server for externally hosted services.
2. **Backends** decide how a server runs work: native, Docker, Kubernetes, or a
   connector. A server's abilities come from the capability mixins it implements.
3. **Services** run on top: tracking, serving, databases, workflows, and more.

Every server and service is a YAML config plus a Python class, so the catalog is
inspectable and extensible. External packages add their own through plugin entry
points. MLOX is deliberately opinionated: it knows how services depend on each
other, so it can wire them together and manage them as one connected system.

For deeper reading:

- [Architecture Guide](docs/ARCHITECTURE.md) — codebase walkthrough and invariants
- [Python API](docs/PYTHON_API.md) — the supported `ProjectWorkspace` SDK contract
- [Plugin Guide](docs/PLUGIN_CONFIGS.md) — shipping services and servers from your own package

---

## Quickstart

```bash
# 1. Install uv (https://docs.astral.sh/uv/)

# 2. Install MLOX with the terminal UI included
uv tool install 'busysloths-mlox[tui]'

# 3. Launch the TUI and hit the "Create" button on the login screen
#    to make your first encrypted, portable project file
mlox tui

# ... or explore the CLI
mlox --help
```

See the [Installation Guide](docs/INSTALLATION.md) for user and developer setup and the integration-test VMs. See [Encrypted Project Files](docs/PROJECT_FILES.md) for creation, storage, backup, and legacy migration details.

---

## Project Structure

```
mlox/
├── mlox/                    # The busysloths-mlox package
│   ├── cli/                 # Typer CLI: declarative specifications/ + commands/
│   ├── tui/                 # Textual terminal UI: screens, widgets, service panels
│   ├── project/             # ProjectWorkspace, WorkspaceState, SQLCipher repository,
│   │                        #   embedded secrets, knowledge entries, operations records
│   ├── application/         # Frontend-independent use cases returning OperationResult
│   ├── infra.py             # Infrastructure topology: bundles of servers and services
│   ├── server.py            # AbstractServer and backend/capability mixins
│   ├── service.py           # AbstractService lifecycle contract and capability ABCs
│   ├── servers/             # Ubuntu (native/Docker/Kubernetes), local, and connector servers
│   ├── services/            # Built-in services: YAML config, class, manifests, client.py
│   ├── config.py            # YAML config loading and plugin entry-point discovery
│   ├── execution/           # Target-agnostic execution base + Docker/K8s/Git/firewall helpers
│   ├── executors.py         # UbuntuTaskExecutor, the current (Fabric/SSH) executor
│   ├── secret_manager.py    # Secret manager interface and TinySecretManager
│   ├── ui/                  # Frontend handler registry
│   ├── view/, app.py        # Streamlit web UI: deprecated, maintenance only
│   ├── assets/              # Cloud-init and Multipass helper scripts
│   └── resources/           # Logos and README media
├── tests/
│   ├── unit/                # Fast tests, no external deps
│   └── integration/         # Multipass VM tests, including Kubernetes/k3s
├── examples/                # Telemetry, tracking, Airflow DAGs, operations demo
├── docs/                    # Doctrine, architecture, catalog, and guides
├── content/                 # Demo and tutorial scripts + media registry
├── scripts/                 # Maintenance utilities, docs checks, content pipeline
├── wiki/                    # GitHub Wiki source pages
└── website/                 # Astro site published to GitHub Pages
```

---

## Contributing

### Sloth-Friendly Setup

```bash
# 1. Install Task (https://taskfile.dev/installation/)
# 2. Clone the repo
git clone https://github.com/BusySloths/mlox.git && cd mlox
# 3. Set up the dev environment (uv-based, installs the package with dev extras)
task first:steps
```

### Run Tests

```bash
task dev:lint                   # flake8
task tests:unit:run             # unit tests (fast, no external deps)
task tests:integration:run      # integration tests (requires Multipass VMs)
task tests:integration:k8s      # Kubernetes integration tests (requires Multipass/k3s)
```

To keep integration runs quiet and save output per test module:

```bash
task tests:integration:run -- --integration-quiet
# Or choose the parent directory for the logs:
task tests:integration:run -- --integration-log-dir /tmp/mlox-logs
# These flags also work with pytest directly and the k8s/service tasks:
uv run python -m pytest tests/integration --run-integration --integration-quiet
```

Each run creates a unique `mlox-integration-*` directory under the system temp
folder (or the supplied parent directory). The terminal shows each test name as it starts, its pass/fail result, and the log
paths. Module files contain captured stdout, stderr, Python logs at
INFO level and above, and full failure tracebacks, including fixture setup and
teardown. Shared fixture output belongs to the module whose test triggers that
fixture phase. Files are written after each phase completes. Quiet capture
applies to the whole pytest invocation; only integration modules get log files.
Omit both options to retain the existing live output.


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
| [Architecture](docs/ARCHITECTURE.md) | Codebase walkthrough and invariants |
| [Python API](docs/PYTHON_API.md) | Supported `ProjectWorkspace` SDK contract |
| [Installation Guide](docs/INSTALLATION.md) | Setup from scratch |
| [Content Pipeline Recipe](docs/CONTENT_PIPELINE.md) | Script, record, redact, verify, and publish demos/tutorial media |
| [Project Files](docs/PROJECT_FILES.md) | Encrypted project files, backup, migration |
| [Contributing Guide](CONTRIBUTING.md) | How to contribute |
| [Plugin Guide](docs/PLUGIN_CONFIGS.md) | External service and server config plugins |
| [Releasing](docs/RELEASING.md) | Versioning and the release pipeline |
| [API Docs](https://busysloths.github.io/mlox/docs) | Generated Python API reference |

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
