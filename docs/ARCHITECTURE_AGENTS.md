# MLOX Core Architecture (LLM/Agent Execution Guide)

This document is optimized for coding agents that must modify core/complex MLOX features safely.

## 1) Mission-critical mental model

Treat MLOX as a **configuration-driven control plane**:

1. Config YAML (`mlox/services/**/mlox.*.yaml`, `mlox/servers/**/mlox-server.*.yaml`) describes capabilities.
2. `mlox/config.py` loads config + plugin entry points and maps `build.class_name` to implementation classes.
3. `MloxSession` (`mlox/session.py`) loads project + secret manager + infrastructure.
4. `Infrastructure` (`mlox/infra.py`) mutates server/service graph and persists state through secret manager.
5. CLI/TUI/Web are shells over the same session/infrastructure behavior.

If you change core behavior, validate impact across **all three interfaces**.

## 2) Setup and execution surfaces

Use **Go Task** (`task`) and **`taskfile.dist.yml`** as the canonical workflow index.

Important tasks include:

- env setup: `task first:steps` / `task dev:env:create`
- unit tests: `task tests:unit:run`
- integration tests (slow, VM-backed): `task tests:integration:run`
- integration cleanup: `task tests:integration:cleanup`
- docker local up/down: `task docker:up` / `task docker:down`

Repository surroundings to understand before edits:

- `tests/unit/`: fast tests
- `tests/integration/`: Multipass-required tests
- `examples/`: usage examples (update when APIs/flows change)
- `docs/`: architecture/process docs
- `scripts/`: experimental/hacky scripts; do not use as architectural source of truth
- `website/`: Astro landing page (not the Streamlit app)

## 3) State and persistence invariants

### Session invariants

`MloxSession` is the authoritative runtime entry:

- it always attempts to load project metadata (`*.project`)
- it binds a secret manager
- it loads/saves `Infrastructure` through that secret manager

### Secret manager invariant

Every MLOX session should end up with a secret manager instance (fallback is in-memory).

### Serialization invariant

Dataclass-like runtime objects are persisted as JSON-compatible dicts, encrypted/secured by secret-manager strategy.

## 4) Config-system invariants (high risk area)

`mlox/config.py` is high-impact:

- defines schema (`ServiceConfig`, `BuildConfig`)
- loads YAML configs for both services and servers
- performs plugin discovery via entry points
- instantiates service/server classes from `build.class_name`

When changing config behavior:

1. keep backward compatibility for existing YAML keys where possible
2. preserve plugin discovery paths (`mlox.service_plugins`, `mlox.server_plugins`)
3. verify service + server loading (not just one)

## 5) Infrastructure mutation rules

In `mlox/infra.py`, service/server changes must preserve:

- registration in singleton service registry
- unique service naming policy
- dynamic port assignment (collision avoidance)
- compatibility with persisted infrastructure reload (`to_dict`/`from_dict`)

Port handling rule:

- Config YAML declares intended ports.
- Effective ports may be reassigned on add/setup to avoid collisions.
- Do not assume static port identity at runtime.

## 6) Service/Server authoring contract

For each service/server:

1. Provide MLOX YAML config.
2. Map YAML `build.class_name` to concrete Python class.
3. Keep backend-specific deployment assets with the service (compose/manifests/scripts).
4. Ensure service exposes `get_secret()` with all access-critical data.
5. If service depends on other services, maintain dependency UUIDs and load through dependency resolver helper (`get_dependend_service` pattern).
6. If user-facing Python integration is needed, expose client wrapper (`client.py` or equivalent).

## 7) Execution boundary rules

- Route system/OS command execution through executors.
- Avoid embedding arbitrary direct shell/subprocess logic into service business flow when executor abstraction exists.
- Keep backend-specific command logic in server/backend adapters.

## 8) Legacy and partial features to treat carefully

- `mlox/scheduler.py`: legacy/obsolete path for most new work.
- `mlox/operations.py`: newer operations layer used by CLI.
- YAML `requirements`: present in schema but not fully enforced today.
- YAML `groups`: partly descriptive; partly intended as functional mapping. Current implementation is inconsistent—avoid over-assuming strict semantics.

## 9) Backend-agnostic extension strategy

Current backends: native, docker, kubernetes.

Architecture intent is backend-agnostic; when adding a backend:

- avoid leaking backend assumptions into shared abstractions
- implement backend logic in server/service adapters
- keep session/infrastructure APIs stable

## 10) Documentation and release surfaces

- pdoc is used to generate API docs for GitHub Pages workflows.
- Project is packaged and can be deployed to PyPI.
- Any public API/core-flow change should be reflected in:
  - docs under `docs/`
  - examples under `examples/` (if user-visible)
  - tests (`tests/unit` and, when applicable, integration coverage)

## 11) Safe-change checklist for agents

Before coding:

- identify whether change touches config/session/infra (high risk)
- map likely blast radius: CLI + TUI + web + persistence + tests

During coding:

- keep YAML schema compatibility unless intentionally versioning
- preserve dependency UUID and secret semantics
- preserve executor boundaries

Before finishing:

- run at least unit tests relevant to touched modules
- run broader unit suite when feasible
- run integration tests only when VM prerequisites are satisfied
- update docs/examples for behavior changes
