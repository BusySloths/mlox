# Installation Guide

> **Source:** [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md)  
> Setup instructions for local development, Docker, and Kubernetes.

---

## Contents

1. [Try MLOX (PyPI)](#try-mlox-pypi)
2. [From Source (GitHub)](#from-source-github)
3. [Docker Hub](#docker-hub)
4. [Kubernetes](#kubernetes)

---

## Try MLOX (PyPI)

The fastest way to try MLOX without cloning the repository is to install it from PyPI and launch the web UI.

### System Requirements

| Component | Minimum |
|-----------|---------|
| RAM | 4 GB (8 GB recommended for heavier stacks like Airflow) |
| CPU | 2 cores |
| OS | Linux, macOS, or Windows (WSL 2) |

> **Note for low-RAM or Windows machines:** Docker Desktop (WSL 2 backend) and Kubernetes (K3s) can be memory-intensive. If your local machine is constrained, consider pointing MLOX at a remote Ubuntu 22.04 VM (≥ 2 vCPU / 4 GB RAM) over SSH instead.

### Steps

```bash
# 1. Create and activate a Python environment
conda create -n mlox python=3.12 -y
conda activate mlox

# 2. Install MLOX with all optional dependencies
pip install "busysloths-mlox[all]"

# 3. Launch the web UI
mlox ui
```

`mlox ui` opens the Streamlit web UI in your browser. From there you can create a new project, add servers, and install services.

For a full list of CLI commands:

```bash
mlox --help
```

---

## From Source (GitHub)

### Prerequisites

- [Go Task](https://taskfile.dev/installation/) — the project's task runner (e.g. `brew install go-task`)
- [Anaconda](https://www.anaconda.com/download) — for the Python environment

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/BusySloths/mlox.git && cd mlox

# 2. Show all available tasks
task help

# 3. Set up the dev environment (creates conda env 'mlox-dev' with Python 3.12.5)
task first:steps

# 4. Activate the environment
source activate mlox-dev
```

### Launch Interfaces

| Command | Interface |
|---------|-----------|
| `task ui:streamlit` | Web UI (Streamlit) |
| `task ui:cli` | CLI |
| `task ui:textual:terminal` | TUI (terminal) |

### Docker (local stack)

```bash
task docker:up    # build and start
task docker:down  # stop
```

This builds a Docker image and starts the web UI, accessible in your browser.

### Testing

```bash
# Unit tests (fast, no external deps)
task tests:unit:run

# Integration tests (requires Multipass VMs)
task tests:integration:run
```

### VM Setup for Integration Testing

MLOX uses [Multipass](https://multipass.run/) VMs for integration testing:

```bash
# Install Multipass
task vm:install:macos   # macOS
task vm:install:linux   # Linux

# Start a test VM (copy the IP; credentials: root / pass)
task vm:start

# Purge all VMs
task vm:purge
```

---

## Docker Hub

### Option 1: Ephemeral (no persistence)

```bash
docker run -it --rm -p 8501:8501 drbusysloth/mlox:latest
```

### Option 2: Persistent projects

```bash
# First run — creates a named container
docker run -it --name mlox -p 8501:8501 drbusysloth/mlox:latest

# Subsequent runs — reattach to the same container
docker start mlox
```

Stopping the container does not lose your projects. Start it again whenever needed.

---

## Kubernetes

For Kubernetes deployment, refer to the [Architecture](Architecture) page for backend details and use the `task docker:*` and `task vm:*` tasks as a reference for wiring services.

---

## See Also

- [Home](Home) — Project overview
- [Architecture](Architecture) — Codebase walkthrough
- [Contributing](Contributing) — How to contribute
- [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md) — Source document
