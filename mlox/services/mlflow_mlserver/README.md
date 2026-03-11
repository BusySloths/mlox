# MLflow MLServer Service

Serves a single registered MLflow model over HTTPS using [MLServer](https://mlserver.readthedocs.io/) as the inference backend. Traefik handles TLS termination and HTTP Basic Auth in front. Intended for one model per deployment — spin up multiple instances on different ports to serve multiple models.

---

## What's in this directory

| File | Purpose |
|------|---------|
| `mlox.mlserver.3.8.1.yaml` | MLOX service config (used by MLOX to discover and instantiate this service) |
| `mlox.mlserver.2.22.0.yaml` | Same but for the older MLflow 2.x / MLServer stack |
| `mlox.mlserver.3.8.1.k3s.yaml` | Kubernetes variant config |
| `docker-compose-mlflow-mlserver-3.8.1.yaml` | Docker Compose stack: Traefik + MLServer app |
| `docker-compose-mlflow-mlserver-2.22.0.yaml` | Docker Compose stack for the 2.x variant |
| `dockerfile-mlflow-mlserver-3.8.1` | Container image: Debian + pyenv + mlflow + mlserver |
| `dockerfile-mlflow-mlserver` | Dockerfile for the 2.x variant |
| `start_mlserver.sh` | Container entrypoint: reads model Python version, installs it, starts serving |
| `docker.py` | MLOX service class (`MLFlowMLServerDockerService`) |
| `k3s.py` | Kubernetes deployment adapter |
| `ui.py` | MLOX Web UI / TUI setup and settings panels |

---

## Architecture

```
MLOX (cli / tui / web)
    │
    └── MLFlowMLServerDockerService.setup()
            │  copies compose file, dockerfile, start_mlserver.sh, writes .env
            └── MLFlowMLServerDockerService.spin_up()
                    │  docker compose up --build
                    └── Container starts: start_mlserver.sh
                            │
                            ├── [bootstrap Python 3.12.5]
                            │       mlflow.artifacts.download_artifacts()
                            │       → reads python_env.yaml → target Python version
                            │
                            ├── pyenv install <version>  (if not cached)
                            │
                            ├── export PYENV_VERSION=<version>
                            │
                            ├── pip install mlflow + mlserver + mlserver-mlflow + uvloop
                            │
                            ├── pip install -r requirements.txt  (model deps, e.g. sktime)
                            │
                            └── exec mlflow models serve
                                    --enable-mlserver
                                    --env-manager=local
                                            │
                                            └── MLServer (port 5002, HTTP)
                                                    │
                                          Traefik (port <MLSERVER_ENDPOINT_PORT>, HTTPS)
                                          Basic Auth + TLS termination
```

External clients hit Traefik over HTTPS. Traefik forwards to MLServer over plain HTTP on the internal Docker network.

---

## Why `--env-manager=local`

MLflow supports three env managers for model serving: `conda`, `virtualenv`, and `local`.

`--enable-mlserver` launches MLServer as a **long-running process** that loads models into its own Python runtime via the `mlserver-mlflow` plugin. When MLServer loads a model, it uses `cloudpickle.load()` in its **worker subprocess** — which is spawned via Python's `multiprocessing` and inherits the parent's Python executable, not a virtualenv activation.

If you use `--env-manager=virtualenv`, MLflow creates a correct virtualenv with the model's dependencies, but MLServer's worker processes run outside that virtualenv's `site-packages`. The result: `ModuleNotFoundError` for any model-specific package (like `sktime`) even though it was correctly installed in the virtualenv.

`--env-manager=local` says "don't create a separate environment — use the current Python." The startup script ensures the current Python **is** the correct version with all required packages already installed before MLServer starts.

---

## The pyenv bootstrap pattern

The Dockerfile pre-installs Python 3.12.5 via pyenv as the bootstrap interpreter. This serves two purposes:

1. The container has `mlflow` available immediately to download model artifacts and read `python_env.yaml` without waiting for compilation.
2. For models logged from Python 3.12.5 (the common case), the pip install step at startup is a near no-op — packages are already present.

For models logged from a different Python version (e.g., 3.11.9), `start_mlserver.sh` calls `pyenv install` at container startup. First run compiles from source (~5–10 min). Subsequent restarts reuse the cached build.

**To cache compiled Pythons across container restarts**, mount the pyenv directory as a named volume in `docker-compose-mlflow-mlserver-3.8.1.yaml`:

```yaml
volumes:
  - pyenv_cache:/root/.pyenv

# at the bottom of the file:
volumes:
  pyenv_cache:
```

---

## Environment variables (`.env` file written by MLOX)

| Variable | Description |
|----------|-------------|
| `MLFLOW_REMOTE_URI` | MLflow tracking server URL |
| `MLFLOW_REMOTE_USER` | Tracking server username |
| `MLFLOW_REMOTE_PW` | Tracking server password |
| `MLFLOW_REMOTE_INSECURE` | Set `true` to skip TLS verification (self-signed certs) |
| `MLFLOW_REMOTE_MODEL` | Registered model path, e.g. `my-model/1` or `my-model/Production` |
| `MLSERVER_ENDPOINT_PORT` | External HTTPS port Traefik listens on |
| `MLSERVER_ENDPOINT_URL` | Hostname for Traefik's Host routing rule |
| `TRAEFIK_USER_AND_PW` | Traefik Basic Auth entry (APR1-MD5 hashed, `$$`-escaped) |

---

## Health check

MLServer exposes a KFServing V2-compatible readiness endpoint:

```bash
curl -k -u admin:password https://<host>:<port>/v2/health/ready
# → 200 OK when model is loaded and ready
```

MLOX's `check()` method uses this endpoint to determine service state.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'sktime'` (or any model dependency)**

The model's `requirements.txt` was not installed into the active Python before MLServer started. Check container logs for the `pip install -r requirements.txt` step. Common causes:

- `python_env.yaml` not present in model artifacts (model was logged without pip requirements)
- pip install failed silently — check for version conflicts in the log

**`pyenv: version X.Y.Z not installed` at startup**

pyenv tried to use a cached version that was removed. Either add a pyenv volume to persist builds, or the pyenv install step itself failed — check for build dependency errors earlier in the log.

**`pyenv install` hangs or takes very long**

Python is being compiled from source. Expected on first use of a given Python version. Mount `/root/.pyenv` as a volume to persist builds across restarts.

**Traefik returns 502 / connection refused**

MLServer hasn't finished starting yet (model loading takes time, especially if pyenv is compiling). Traefik will retry — wait and check `/v2/health/ready`. If it persists, check that `mlserver_app` container is actually running (`docker ps`).

**`cloudpickle` version mismatch error on model load**

The model was pickled with a different cloudpickle version than what's installed. Pin `cloudpickle` in your model logging environment and check that `requirements.txt` includes it. MLflow logs cloudpickle as part of model dependencies — it should appear in `requirements.txt` automatically.

**Wrong Python version used (e.g., Debian's system Python)**

This was the original bug before the current design. Symptom: error paths show `/usr/bin/python3.11/...` instead of `/root/.pyenv/versions/.../`. Root cause: using `python:3.X-slim` as the Docker base, which includes both Docker's Python and Debian's Python 3.11 — and MLServer's subprocess spawn picks the wrong one. The current `debian:bookworm-slim` + pyenv-only setup eliminates this.

---

## Versions and variants

| Variant | MLflow | MLServer | Dockerfile | Compose | Notes |
|---------|--------|----------|-----------|---------|-------|
| 3.8.1 (current) | 3.8.1 | 1.7.x | `dockerfile-mlflow-mlserver-3.8.1` | `docker-compose-mlflow-mlserver-3.8.1.yaml` | pyenv, dynamic Python |
| 2.22.0 (legacy) | 2.22.0 | bundled | `dockerfile-mlflow-mlserver` | `docker-compose-mlflow-mlserver-2.22.0.yaml` | older stack, no pyenv |
