# Installation Guide

> **Source:** [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md)  
> Setup instructions for local development, Docker, and Kubernetes.

---

## Contents

1. [From Source (GitHub)](#from-source-github)
2. [Docker Hub](#docker-hub)
3. [Kubernetes](#kubernetes)

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

# Kubernetes integration tests (requires Multipass/k3s)
task tests:integration:k8s
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

### macOS Privacy & Security for Multipass

On macOS, Multipass-backed setup depends on the app that starts MLOX. If the TUI
runs in iTerm2, then iTerm2 needs the same permission as VS Code would need when
running Streamlit.

Open **System Settings** -> **Privacy & Security** -> **Developer Tools** and
allow:

- Multipass
- Docker or Docker Desktop, when Docker-backed services are used
- the terminal app that runs the TUI, for example iTerm2 or Terminal.app
- VS Code or another editor/IDE, when it launches Streamlit, tests, or the CLI

Quit and reopen the affected app after changing the setting. If the VM starts but
cannot be reached, also check **Privacy & Security** -> **Local Network** for the
same client app.

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


## Encrypted project files

New projects are portable SQLCipher `.mlox` files. Create one with `mlox project new ./projects/demo`, then set `MLOX_PROJECT_PATH` and `MLOX_PROJECT_PASSWORD`. See [Project Files](Project-Files) for storage, backup, and legacy migration.
