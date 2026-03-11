# MLflow MLServer Service — Agent Reference

Optimized for coding agents modifying this service. Read fully before making changes.

---

## 1) Mental model

This service deploys one registered MLflow model per container instance using MLServer as the inference runtime. The stack is: `Traefik (HTTPS/BasicAuth) → MLServer (HTTP, port 5002) → mlserver-mlflow plugin → cloudpickle model`.

The container is **model-agnostic at build time**. The model's Python version and pip dependencies are resolved at **container startup** by `start_mlserver.sh` using pyenv and the model's logged `requirements.txt`.

---

## 2) File map and ownership

```
mlflow_mlserver/
├── mlox.mlserver.3.8.1.yaml          # MLOX service descriptor → maps to docker.py class
├── mlox.mlserver.3.8.1.k3s.yaml      # K8s variant descriptor → maps to k3s.py class
├── mlox.mlserver.2.22.0.yaml         # Legacy 2.x variant
├── docker-compose-mlflow-mlserver-3.8.1.yaml   # Traefik + mlserver_app services
├── docker-compose-mlflow-mlserver-2.22.0.yaml  # Legacy
├── dockerfile-mlflow-mlserver-3.8.1   # debian:bookworm-slim + pyenv + bootstrap Python
├── dockerfile-mlflow-mlserver         # Legacy 2.x dockerfile
├── start_mlserver.sh                  # Container entrypoint (the critical file)
├── docker.py                          # MLFlowMLServerDockerService (AbstractService)
├── k3s.py                             # K8s adapter
└── ui.py                              # MLOX UI panels (setup + settings)
```

**The 3.8.1 stack is the active one. The 2.22.0 stack is legacy — do not apply 3.8.1 changes there without explicit instruction.**

---

## 3) Call hierarchy

### MLOX orchestration layer (docker.py)

```
MLFlowMLServerDockerService.setup(conn)
    exec.fs_create_dir(target_path)
    exec.fs_copy(template → target_path/docker-compose-*.yaml)
    exec.fs_copy(dockerfile → target_path/dockerfile-*)
    exec.fs_copy(start_script → target_path/start_mlserver.sh)   # only if start_script set
    _generate_htpasswd_entry()          # APR1-MD5 hash, $-escaped for Traefik
    exec.fs_create_empty_file(.env)
    exec.fs_append_line(.env, ...)      # writes all env vars

MLFlowMLServerDockerService.spin_up(conn)
    → compose_up(conn)                  # docker compose up -d --build

MLFlowMLServerDockerService.spin_down(conn)
    → compose_down(conn)

MLFlowMLServerDockerService.teardown(conn)
    exec.docker_down(compose_file, remove_volumes=True)
    exec.fs_delete_dir(target_path)

MLFlowMLServerDockerService.check(conn)
    exec.docker_service_state(mlflow_mlserver_<port>)
    → if running: curl -k -u user:pw https://host:port/v2/health/ready
    → returns {"status": "running"|"stopped"|"unknown"}
```

### Container startup (start_mlserver.sh)

```
bash start_mlserver.sh
    python mlflow.artifacts.download_artifacts("models:/$MLFLOW_REMOTE_MODEL")
        → MODEL_LOCAL_PATH
    awk python_env.yaml → PYTHON_VERSION
        fallback: awk MLmodel → python_version field
        fallback: python -c platform.python_version()
    pyenv versions --bare | grep PYTHON_VERSION
        → if missing: pyenv install $PYTHON_VERSION && pyenv rehash
    export PYENV_VERSION=$PYTHON_VERSION
    pip install mlflow==3.8.1 mlflow[extras] mlserver~=1.7.1 mlserver-mlflow~=1.7.1 uvloop==0.21.0
    pip install -r $MODEL_LOCAL_PATH/requirements.txt
    exec mlflow models serve -m models:/$MLFLOW_REMOTE_MODEL -p 5002 -h 0.0.0.0 -w 1
        --enable-mlserver --env-manager=local
```

---

## 4) Invariants — do not break these

**`--env-manager=local` is load-bearing.** Do not change it to `virtualenv` or `conda`.

Reason: `mlflow models serve --enable-mlserver` launches MLServer as a standalone process. MLServer loads models in a `multiprocessing`-spawned worker process. That worker process uses `sys.executable` from the parent, not a virtualenv activation. A virtualenv created by `--env-manager=virtualenv` is invisible to the worker's `sys.path`, causing `ModuleNotFoundError` for every model-specific package. `--env-manager=local` ensures MLServer and all model deps share one Python environment.

**`PYENV_VERSION` must be exported before `mlflow models serve`.** This is what tells pyenv shims which Python `mlflow`, `pip`, and `mlserver` resolve to after the version switch. If the export is removed or moved after the serve command, the serve command runs in the bootstrap Python (3.12.5) regardless of the model's required version.

**`exec` on the final `mlflow models serve` is intentional.** It replaces the shell process with mlflow, making it PID 1 in the container. Docker stop signals go directly to mlflow/mlserver. Removing `exec` means the shell becomes PID 1 and signals may not propagate correctly.

**`docker.py:setup()` copies `start_mlserver.sh` only when `start_script` is set** (line 76–81). The `mlox.mlserver.3.8.1.yaml` sets `start_script: ${MLOX_STACKS_PATH}/mlflow_mlserver/start_mlserver.sh`. If you rename `start_mlserver.sh`, update the yaml `params.start_script` key.

**`__post_init__` name mangling:** The service name is prefixed with `{model}@` and `target_path` is suffixed with `-{port}`. These make multiple instances of the same model on different ports distinguishable in the infrastructure graph.

---

## 5) Environment variable contract

The `.env` file is written by `setup()` and consumed by the Docker Compose stack.

| `.env` key | Source in docker.py | Consumed by |
|------------|---------------------|-------------|
| `TRAEFIK_USER_AND_PW` | `{user}:{hashed_pw}` (APR1-MD5, `$$`-escaped) | Traefik label |
| `MLSERVER_ENDPOINT_URL` | `conn.host` | Traefik Host rule + mlserver_app env |
| `MLSERVER_ENDPOINT_PORT` | `self.port` | Traefik port binding + container name |
| `MLFLOW_REMOTE_MODEL` | `self.model` | `start_mlserver.sh`, mlflow serve arg |
| `MLFLOW_REMOTE_URI` | `self.tracking_uri` | mlflow client in start_mlserver.sh |
| `MLFLOW_REMOTE_USER` | `self.tracking_user` | mlflow client |
| `MLFLOW_REMOTE_PW` | `self.tracking_pw` | mlflow client |
| `MLFLOW_REMOTE_INSECURE` | hardcoded `true` | mlflow client (skips TLS verify) |

**`MLFLOW_REMOTE_MODEL` format:** set by the user as `model_name/version_or_alias` (e.g., `my-model/1` or `my-model/Production`). The `start_mlserver.sh` prefixes it with `models:/` to form a full MLflow model URI.

---

## 6) Docker image design (dockerfile-mlflow-mlserver-3.8.1)

Base: `debian:bookworm-slim` — deliberately not `python:3.X-slim`.

`python:3.X-slim` images include Debian's system Python (3.11 on Bookworm) alongside Docker's Python. When MLServer's `multiprocessing` worker spawns and subprocess PATH resolution falls through pyenv shims to "system", the Debian Python can win, causing import errors. `debian:bookworm-slim` with pyenv as sole Python manager eliminates this.

Build steps:
1. Install all pyenv C-extension build dependencies (apt).
2. Install pyenv from `pyenv.run`.
3. Set `PYENV_ROOT`, prepend `$PYENV_ROOT/shims:$PYENV_ROOT/bin` to `PATH`.
4. `pyenv install 3.12.5 && pyenv global 3.12.5` — bootstrap Python.
5. `pip install mlflow + mlserver + uvloop` — pre-installed for fast startup on 3.12.5 models.
6. `COPY start_mlserver.sh` + `chmod +x`.

**Do not remove pyenv** even though `--env-manager=local` is used. pyenv is still needed to install model-specific Python versions at startup. `--env-manager=local` means "use the current interpreter" — but we change the current interpreter via `PYENV_VERSION` to the model's Python.

---

## 7) High-risk change areas

| Change | Risk | Constraint |
|--------|------|-----------|
| Changing `--env-manager` flag | High | Must stay `local` — see invariants §4 |
| Adding `--env-manager=virtualenv` | Breaks model loading | MLServer worker subprocess doesn't inherit virtualenv |
| Removing `export PYENV_VERSION` | High | mlflow serve runs in wrong Python |
| Changing base image to `python:X.Y-slim` | Medium | Reintroduces dual-Python problem; test thoroughly |
| Changing `start_script` param in yaml | High | `docker.py:setup()` won't copy the script; container will fail to start |
| Modifying `_generate_htpasswd_entry` | Medium | Traefik requires APR1-MD5 with `$$`-escaped `$`; other hash types fail |
| Adding `pip install --upgrade` in script | Low-Medium | May break pinned mlserver/mlflow version compatibility |

---

## 8) Model artifact structure assumptions

`start_mlserver.sh` expects the downloaded model artifacts to contain:

```
<model_artifacts>/
├── MLmodel              # YAML: contains python_version field
├── python_env.yaml      # YAML: contains "python: X.Y.Z" (preferred source)
└── requirements.txt     # pip requirements (model deps to install)
```

`python_env.yaml` is generated by MLflow when logging models with `pip` env manager (default in MLflow 3.x). If absent (e.g., conda-logged model), fallback reads `python_version` from `MLmodel`. If both are absent, the script warns and uses the current Python version.

---

## 9) Adding a new MLflow/MLServer version variant

1. Copy `mlox.mlserver.3.8.1.yaml` → `mlox.mlserver.<version>.yaml`. Update `id`, `name`, `version`, `description`, `build.params.name`, `build.params.template`, `build.params.dockerfile`.
2. Copy `docker-compose-mlflow-mlserver-3.8.1.yaml` → new name. Update the `dockerfile:` reference in `mlserver_app.build`.
3. Copy `dockerfile-mlflow-mlserver-3.8.1` → new name. Update pip version pins for mlflow and mlserver. Keep `debian:bookworm-slim` base and pyenv bootstrap.
4. `start_mlserver.sh` is shared across versions — update the version pins inside it if mlflow/mlserver versions differ, or create a variant.
5. Register the new yaml in the MLOX plugin entry points (`pyproject.toml` or `setup.cfg` under `mlox.service_plugins`).
