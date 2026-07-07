# Installation

MLOX deploys and manages the servers, services, and integrations around your ML/AI product. It is a Python 3.11/3.12 project, and the repository uses [Task](https://taskfile.dev/installation/) as the main command runner.

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

## Docker

For the repository-local Docker Compose stack:

```bash
task docker:up
task docker:down
```

You can also run the published image:

```bash
docker run -it --rm -p 8501:8501 drbusysloth/mlox:latest
```

To keep projects between runs, give the container a name and start it again later:

```bash
docker run -it --name mlox -p 8501:8501 drbusysloth/mlox:latest
docker start -ai mlox
```

## Integration Test VMs

Integration tests use Multipass VMs and are slower than unit tests.

### macOS Privacy & Security

On macOS, Multipass-backed server setup can fail differently depending on the app
that launches MLOX. Add the relevant host apps to **System Settings** ->
**Privacy & Security** -> **Developer Tools**:

- Multipass
- Docker or Docker Desktop, if Docker-backed services are used
- the terminal app that runs the Textual TUI, for example iTerm2 or Terminal.app
- VS Code or another editor/IDE, if it launches Streamlit, tests, or the CLI

Quit and reopen the affected app after changing the setting. For macOS 26 local
network issues, also see the Multipass troubleshooting guide in the wiki.

For running all integration tests just type (assumes multipass VM has been installed):

```bash
task tests:integration:run
```

For running only the Kubernetes integration tests, which provision a k3s-backed
Multipass VM and run tests marked with both `integration` and `kubernetes`:

```bash
task tests:integration:k8s
# alias:
task tests:integration:kubernetes
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
task tests:integration:k8s
task tests:integration:cleanup
task vm:purge
```

Use `task vm:purge` carefully; it removes the local Multipass VMs created for MLOX testing.


## Create an encrypted project

```bash
mlox project new ./projects/demo --password 'choose-a-strong-password'
export MLOX_PROJECT_PATH="$PWD/projects/demo.mlox"
export MLOX_PROJECT_PASSWORD='choose-a-strong-password'
```

See [Encrypted Project Files](PROJECT_FILES.md), including the non-destructive legacy importer.
