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

Use the CLI or TUI to operate the same inspectable, configuration-driven core. MLOX is built for solopreneurs, startups, and small teams that want to focus on their product instead of assembling and maintaining infrastructure.

It's for engineers who prefer thoughtful systems over chaos. Backed by open source. Powered by sloths.

---

## Quick Navigation

| Page | Description |
|------|-------------|
| [Architecture](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE.md) | Codebase walkthrough |
| [Installation](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) | Setup from scratch (local, Docker, Kubernetes) |
| [Contributing](https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md) | How to contribute to MLOX |
| [Troubleshooting](Troubleshooting) | Known setup and runtime issues with fixes and workarounds |
| [Services Catalog](Services-Catalog) | All supported MLOps services |

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

See the [Services Catalog](Services-Catalog) page — the exhaustive, authoritative
list generated from the YAML plugin configs (36 service configs, 9 server configs).

---

## Architecture at a Glance

```text
CLI     TUI                      Other UIs (via plugins)
  \      |                          /
   \     |                         /
    +----+------------------------+
                    |
                    v
             `ProjectWorkspace`
          stateful mutation boundary
                    |
                    v
     internal state + SQLCipher repository
             /                               \
            v                                 v
 embedded SQLCipher storage                `Infrastructure`
 (metadata + topology + secrets)      topology for one project
                                            |
                                            v
                           `Bundle` = compute/server + services[*]
                                      |
                                      v
                    execution via `mlox/executors.py` + `mlox/execution/*`
```

`ProjectWorkspace` exposes the shared mutation and direct SDK API. It loads
internal state containing metadata and `Infrastructure`, and commits both
atomically to the encrypted project file. CLI commands open a workspace per
invocation; the TUI retains one in runtime state.

Service and server definitions remain inspectable and configuration-driven, while execution is handled consistently across Native, Docker, Kubernetes, and connector backends.

→ Read the full [Architecture guide](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE.md) for a deep dive.

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

See [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) for Docker and Kubernetes setup.

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
| Doctrine (status/roadmap/decisions) | [`docs/DOCTRINE.md`](https://github.com/BusySloths/mlox/blob/main/docs/DOCTRINE.md) |
| Services Catalog | [Services Catalog](Services-Catalog) wiki page |
| Architecture | [`docs/ARCHITECTURE.md`](https://github.com/BusySloths/mlox/blob/main/docs/ARCHITECTURE.md) |
| Installation Guide | [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) |
| Contributing Guide | [`CONTRIBUTING.md`](https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md) |
| Plugin Guide | [`docs/PLUGIN_CONFIGS.md`](https://github.com/BusySloths/mlox/blob/main/docs/PLUGIN_CONFIGS.md) |
| Project Files | [`docs/PROJECT_FILES.md`](https://github.com/BusySloths/mlox/blob/main/docs/PROJECT_FILES.md) |
| API Docs | [busysloths.github.io/mlox/docs](https://busysloths.github.io/mlox/docs/mlox.html) |
| Website | [mlox.org](https://mlox.org) |

---

## License

MLOX is open-source under the [MIT License](https://github.com/BusySloths/mlox/blob/main/LICENSE).

---

_Powered by sloths. 🦥_
