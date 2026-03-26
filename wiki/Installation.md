# Installation Guide

> **Source:** [`docs/INSTALLATION.md`](https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md)

---

## Contents

1. [From GitHub (Source)](#from-github-source)
2. [From Docker Hub](#from-docker-hub)

---

## From GitHub (Source)

### Prerequisites

- [Go Task](https://taskfile.dev/installation/) — e.g. `brew install go-task`
- [Anaconda](https://www.anaconda.com/download) (for the Python environment)
- [Git](https://git-scm.com/)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/BusySloths/mlox.git
cd mlox

# 2. Show all available task commands
task help
```

### Build and Start Docker from Scratch

```bash
task docker:up
```

This builds and spins up a Docker container with the Web UI accessible via your browser.

### Run with Python (Conda)

```bash
# Set up the environment (creates conda env 'mlox-dev' with Python 3.12.5)
task first:steps

# Activate the environment
source activate mlox-dev
```

Then launch one of the three interfaces:

| Interface | Command |
|-----------|---------|
| Web UI (Streamlit) | `task ui:streamlit` |
| CLI | `task ui:cli` |
| TUI (Terminal) | `task ui:textual:terminal` |

### Run Unit Tests

```bash
task tests:unit:run
```

### Setup VM for Integration Testing

MLOX uses [Multipass](https://multipass.run/) VMs for integration testing.

```bash
# Install Multipass (choose your OS)
task vm:install:macos
# or
task vm:install:linux

# Start a MLOX-ready VM (use IP shown, credentials: root / pass)
task vm:start

# Clean up all VMs when done
task vm:purge
```

> **macOS users:** If the VM is not reachable after spin-up, see the [Troubleshooting](Troubleshooting#vm--multipass--macos-osx-26--not-reachable-after-spin-up) page.

---

## From Docker Hub

### Option 1: No project persistence needed

```bash
docker run -it --rm -p 8501:8501 drbusysloth/mlox:latest
```

This pulls and runs the image. All project data is lost when the container stops.

### Option 2: Persist projects across runs

```bash
# First run — pull image and create named container
docker run -it --name mlox -p 8501:8501 drbusysloth/mlox:latest

# Subsequent runs — restart the existing container
docker start mlox
```

Your projects are preserved between `docker stop` and `docker start` calls.

> **Docker v29+ users:** If services report "client version is too old" errors, see the [Troubleshooting](Troubleshooting#docker-29--client-version--is-too-old) page.

---

## See Also

- [Home](Home) — Project overview
- [Contributing](Contributing) — Development environment setup
- [Architecture](Architecture) — Codebase walkthrough
- [Troubleshooting](Troubleshooting) — Known issues and fixes
