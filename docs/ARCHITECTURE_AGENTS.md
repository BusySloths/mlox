# MLOX Core Architecture (LLM/Agent Execution Guide)

This document is optimized for coding agents that must modify core/complex MLOX features safely.

## 1) Mission-critical mental model

Treat MLOX as a **configuration-driven control plane**:

1. Config YAML (`mlox/services/**/mlox.*.yaml`, `mlox/servers/**/mlox-server.*.yaml`) describes capabilities.
2. `mlox/config.py` loads config + plugin entry points and maps `build.class_name` to implementation classes.
3. Frontend-specific UI handlers live in the frontend packages and are resolved through `mlox/ui/registry.py`; do not model them back into YAML.
4. `mlox/application/use_cases/*` is the important shared application layer for session-based logic. All UIs should converge on it.
5. `MloxSession` (`mlox/session.py`) is the runtime container: project metadata + secret manager + `Infrastructure`.
6. `Infrastructure` (`mlox/infra.py`) is the topology root for one project/session and holds `Bundle` objects.
7. A `Bundle` groups one compute/server plus the services deployed onto it.
8. Anything executed on a compute/server must go through the execution layer (`mlox/executors.py` + `mlox/execution/*`).
9. `mlox/application/facade.py` is a current adapter for CLI/session loading, and `mlox/application/infrastructure_ops.py` contains side-effectful orchestration helpers used by the use-cases.

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
- it always ends up with a secret manager instance
- it loads/saves `Infrastructure` through that secret manager
- it is the one object that ties together project metadata, secrets, and topology

### Secret manager invariant

Every MLOX session should end up with a secret manager instance (fallback is in-memory).

Treat that secret manager as the encrypted key-value persistence boundary around the session.

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
4. keep UI lookup behavior aligned with `ServiceConfig.get_ui_handler(...)` and `mlox/ui/registry.py`

## 5) Infrastructure mutation rules

In `mlox/infra.py`, service/server changes must preserve:

- `Infrastructure` as the topology root for bundles, compute, and services
- binding services to infrastructure-backed dependency lookup
- unique service naming policy
- dynamic port assignment (collision avoidance)
- compatibility with persisted infrastructure reload (`to_dict`/`from_dict`)

Bundle shape rule:

- a bundle represents one compute/server plus its attached services
- compute capabilities are explicit and used for placement/runtime behavior
- service capabilities are an emerging model, so do not hard-code assumptions that they are complete yet

Port handling rule:

- Config YAML declares intended ports.
- Effective ports may be reassigned on add/setup to avoid collisions.
- Do not assume static port identity at runtime.

## 6) Service/Server authoring contract

For each service/server:

1. Provide MLOX YAML config.
2. Map YAML `build.class_name` to concrete Python class.
3. Keep backend-specific deployment assets with the service/server (compose/manifests/scripts).
4. Keep frontend-specific UI handlers in frontend-owned modules (`mlox/view/...`, `mlox/tui/...`) and register them through `mlox/ui/registry.py`.
5. Ensure compute/server capabilities remain accurate (`git`, `docker`, `kubernetes`, `firewall`, etc.).
6. Ensure service exposes `get_secret()` with all access-critical data.
7. If service depends on other services, maintain dependency UUIDs and load through dependency resolver helper (`get_dependend_service` pattern).
8. If user-facing Python integration is needed, expose client wrapper (`client.py` or equivalent).

## 7) Execution boundary rules

- Route system/OS command execution through executors.
- Anything that runs on a compute/server should do so via the execution layer, not through ad-hoc shell calls from random UI/application code.
- Avoid embedding arbitrary direct shell/subprocess logic into service business flow when executor abstraction exists.
- Keep backend-specific command logic in server/backend adapters.

## 8) Legacy and partial features to treat carefully

- `mlox/scheduler.py`: legacy/obsolete path for most new work.
- `mlox/application/use_cases/*`: important shared session-based application layer; prefer extending this over recreating broad operations modules.
- `mlox/application/facade.py`: thin stateless adapter that loads/caches session context and dispatches to `application/use_cases/*`.
- `mlox/application/infrastructure_ops.py`: orchestration helpers used by session-based use-cases; treat this as application-layer runtime logic, not pure domain state.
- `mlox/ui/registry.py`: bootstrap/lookup layer for frontend-owned UI handlers; keep config concerns and UI concerns separated.
- YAML `requirements`: present in schema but not fully enforced today.
- server capabilities: real and important
- service capabilities: emerging; today the signal is incomplete and partly represented through YAML groups and typed interfaces

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
- map likely blast radius: CLI command modules + facade/use-cases + TUI + web + persistence + tests

During coding:

- keep YAML schema compatibility unless intentionally versioning
- preserve dependency UUID and secret semantics
- preserve executor boundaries

Before finishing:

- run at least unit tests relevant to touched modules
- run broader unit suite when feasible
- run integration tests only when VM prerequisites are satisfied
- update docs/examples for behavior changes
