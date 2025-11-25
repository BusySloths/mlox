# The Sloth Way of Installation Enlightment

## Github

- Clone the repository via `git clone https://github.com/BusySloths/mlox.git`
- Install go-tasks which is super-easy for many systems: <https://taskfile.dev/docs/installation> e.g. `brew install go-task`

- ease into the the project root `cd mlox`
- show all commands: `task help`

### Build and Start Docker from Scratch

- just run `task docker:up` will build and spin up a docker container with the web UI that you can access via your browser

### Run Python

- we assume that Anaconda is installed (cf. <https://www.anaconda.com/download>)

- run `task first:steps` (sets up a condo environment with all packages, ready to run mlox)
- activate your new environment e.g. `source activate mlox-dev`

Run one of the following:

- Web UI: `task ui:streamlit` (start local web app)
- CLI: `task ui:cli` (show CLI)
- TUI: `task ui:textual:terminal` (start local terminal UI)

- Unit Tests: `task tests:unit:run`

### Setup VM for Testing

- we use canonical `multipass` VM for testing
- run `task vm:install:(macos OR linux)` to install multipass on your system
- start a mlox-ready vm via: `task vm:start` copy the IP and use `root`/`pass` for user/pw.

- delete all vms via `task vm:purge`

## Docker Hub

- use `docker pull drbusysloth/mlox:latest`
