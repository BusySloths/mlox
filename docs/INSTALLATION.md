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

### Option 1: I don't need to persist projects

- use `docker run -it --rm -p 8501:8501 drbusysloth/mlox:latest` this pulls and runs the image

### Option 2: I want to persist projects

- first time usage: `docker run -it --name mlox -p 8501:8501 drbusysloth/mlox:latest` this will pull the image and start a container with name `mlox`
- You can now use MLOX and stop the container as you like without loosing your projects. If you want to run again and load your projects just start the container again with `docker start mlox`
