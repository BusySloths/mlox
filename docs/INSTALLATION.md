# Installation

MLOX is a Python 3.11/3.12 project. The repository uses [Task](https://taskfile.dev/installation/) as the main command runner.

## Try MLOX (PyPI)

The fastest way to try MLOX without cloning the repository is to install it from PyPI and launch the web UI.

### Prerequisites

- Python 3.11 or 3.12
- A Conda or virtualenv environment (recommended)

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

### Docker (no Python env needed)

If you prefer not to set up a Python environment, run MLOX directly via Docker:

```bash
# Ephemeral (no persistence)
docker run -it --rm -p 8501:8501 drbusysloth/mlox:latest

# Persistent projects
docker run -it --name mlox -p 8501:8501 drbusysloth/mlox:latest
docker start -ai mlox
```

Open `http://localhost:8501` in your browser.

---

## From Source

```bash
git clone https://github.com/BusySloths/mlox.git
cd mlox
task
task first:steps
```

The plain `task` command prints the command overview. `task first:steps` creates the development environment and installs the package with development extras. Activate the created environment before running local commands. With Conda, that is usually:

```bash
conda activate mlox-dev
```

Useful local commands:

```bash
task ui:streamlit          # Streamlit web UI
task ui:cli                # CLI help
task ui:textual:terminal   # Textual TUI
task tests:unit:run        # unit tests
```

## Docker (from source)

For the repository-local Docker Compose stack:

```bash
task docker:up
task docker:down
```

## Integration Test VMs

Integration tests use Multipass VMs and are slower than unit tests.

For running all integration tests just type (assumes multipass VM has been installed):

```bash
task tests:integration:run
```

For running a specific integration test use:

```bash
task tests:integration:service SERVICE=service_name
```

All related commands:

```bash
task vm:install:macos      # macOS only
task vm:install:linux      # Linux only
task vm:start
task tests:integration:run
task tests:integration:cleanup
task vm:purge
```

Use `task vm:purge` carefully; it removes the local Multipass VMs created for MLOX testing.
