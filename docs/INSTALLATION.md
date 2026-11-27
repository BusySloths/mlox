# Installation

MLOX deploys and manages the servers, services, and integrations around your ML/AI product. It is a Python 3.11/3.12 project, and the repository uses [Task](https://taskfile.dev/installation/) as the main command runner.

There are two supported paths, depending on who you are:

- **Users** — install the published package with [uv](https://docs.astral.sh/uv/) and start using the CLI/TUI.
- **Developers** — clone the repository and bootstrap a reproducible dev environment (also uv-based).

> We deliberately keep this list short. Docker-based delivery was removed along
> with the Streamlit web UI, now archived in `legacy/ui/` (see `docs/DOCTRINE.md`).

## Users

Install with [uv](https://docs.astral.sh/uv/) (recommended — works the same on
macOS, Linux, and Windows):

```bash
uv tool install 'busysloths-mlox[tui]'
```

The `[tui]` extra pulls in the terminal UI; without it you get the CLI only.
If you prefer pipx, the equivalent is:

```bash
pipx install 'busysloths-mlox[tui]'
```

Verify and upgrade:

```bash
mlox --help          # CLI
mlox tui             # terminal UI
mlox ui              # the same UI in your browser (http://localhost:8000)
uv tool upgrade busysloths-mlox
```

Launch the TUI and hit the **Create** button on the login screen to make your
first encrypted project — no manual setup needed. The CLI (`mlox --help`) can
operate the same project, as can the Python SDK.

When a project's firewall is enabled, use `mlox firewall access-add` with a
duration such as `15m` to grant the current computer temporary access to
firewall-capable servers, or `mlox firewall access-hold` for access maintained
while the command runs. Remove the grant with `mlox firewall access-remove`.
Temporary grants are not saved by firewall policy persistence. See the
[CLI guide](../mlox/cli/README.md) for expiration, NAT, and per-computer details.

## Developers (from source)

```bash
git clone https://github.com/BusySloths/mlox.git
cd mlox
task
task first:steps
```

The plain `task` command prints the command overview. `task first:steps` uses
[uv](https://docs.astral.sh/uv/) to create the environment from `uv.lock`
(reproducible on macOS, Linux, and Windows — no conda needed) and installs the
package with development extras.

There is nothing to activate: run commands through `uv run`, e.g.:

```bash
uv run mlox --help
uv run mlox tui             # Textual TUI
uv run mlox ui              # the TUI in the browser (textual-serve)
task tests:unit:run         # unit tests (uses uv run internally)
task dev:lint               # flake8
```

If you change dependencies in `pyproject.toml`, regenerate the lockfile with
`task deps:lock` and commit both files together (CI enforces that
`uv.lock` matches `pyproject.toml`).

## Integration Test VMs

Integration tests use Multipass VMs and are slower than unit tests.

### macOS Privacy & Security

On macOS, Multipass-backed server setup can fail differently depending on the app
that launches MLOX. Add the relevant host apps to **System Settings** ->
**Privacy & Security** -> **Developer Tools**:

- Multipass
- Docker or Docker Desktop, if Docker-backed services are used
- the terminal app that runs the Textual TUI, for example iTerm2 or Terminal.app
- VS Code or another editor/IDE, if it launches the TUI, tests, or the CLI

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

For the Ubuntu firewall integration suite, run this on a machine capable of
running Multipass VMs and pulling Docker images:

```bash
uv run pytest tests/integration/test_ubuntu_firewall.py --run-integration -v
```

The suite provisions separate disposable native and Docker Ubuntu VMs, changes
their firewall rules, creates guest-local test networks and services, and reboots
the VMs. It deletes only the VMs it created. It does not use existing project
servers. IPv4 and IPv6 support is required in the guests; the Docker cases
require Docker's `DOCKER-USER` chain for both address families.

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

The TUI's **Create** button does this interactively. For scripts and CI, use the
CLI instead:

```bash
mlox project new ./projects/demo --password 'choose-a-strong-password'
export MLOX_PROJECT_PATH="$PWD/projects/demo.mlox"
export MLOX_PROJECT_PASSWORD='choose-a-strong-password'
```

See [Encrypted Project Files](PROJECT_FILES.md), including the non-destructive legacy importer.
