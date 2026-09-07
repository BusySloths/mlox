# MLOX Doctrine

> **The single point of truth for MLOX status, roadmap, and binding decisions.**
> Every other document — README, `docs/ARCHITECTURE.md`, the website, and the
> wiki — is a *view*: it may summarize and link here, but it must
> **not restate** facts. When you change status, roadmap, or a core decision,
> change it here first.

**Documentation rule:** *one fact = one home. Everything else links or is
generated.* Facts about the service/server catalog are generated from the YAML
configs (`docs/SERVICES_CATALOG.md`); status, roadmap, and decisions live here;
architecture lives in `docs/ARCHITECTURE.md`; everything else derives.

---

## Component Status

| Component | Status | Notes |
| ----------- | -------- | ------- |
| **CLI** (`mlox/cli/`) | **Primary interface** | Maintained, fully supported. |
| **TUI** (`mlox/tui/`) | **Primary interface** | Maintained, fully supported. |
| **Web UI / Streamlit** (`mlox/view/`, `mlox/app.py`) | **Deprecated** | Will be extracted to a plugin repo. See [Decision ADR](#adr-streamlit-web-ui-extraction). No new features or investments. |
| Kubernetes execution | **Stable** | Works well in practice, including Kubernetes-native services. |
| Connector backends | **Beta** | Externally hosted integrations. |
| Native / Docker execution | **Stable** | Primary execution paths. |
| Persistence (SQLCipher `project.mlox`) | **Stable** | Single encrypted file per project. |
| Project sync (PostgreSQL snapshot) | **Planned** | Local-first SQLCipher + optional Postgres sync point; see Roadmap. |

Not every bundled service has a uniform status; maturity labels (Functional /
Beta / Experimental) per component are tracked here as they change, not in the
generated catalog.

---

## Binding Decisions (ADR-lite)

Each entry records a decision and the date it was made. These are conserved
until explicitly reversed here.

### ADR: Streamlit web UI extraction

**Date:** 2026-09 — **Status:** Accepted
The Streamlit web UI (`mlox/view/` and `mlox/app.py`) is being **phased out and
moved into a separate plugin repository**. The TUI and CLI are the primary points
of contact for the platform. Consequently:

- No new features or architectural investment in `mlox/view/` or `mlox/app.py`.
- Changes there are **maintenance only** (bug fixes, keeping tests green).
- UI-specific handlers in `mlox/ui/registry.py` move with the streamlit plugin.
- Documentation and agents must not describe the web UI as a maintained
  interface going forward (see `docs/ARCHITECTURE.md`).

### ADR: SQLModel deferred

Deliberately not introducing SQLModel ORM records yet. The infrastructure graph
remains behavior-heavy and polymorphic; the dataclass-based JSON snapshot is
authoritative. This is expected to stay for the foreseeable future.
Reconsider only when partial queries, concurrent updates, or PostgreSQL
become active requirements.

### ADR: One transaction for metadata + infrastructure

Metadata and infrastructure are persisted atomically in one transaction. This is
the `ProjectWorkspace.commit()` boundary (`workspace.py`: commit → single
`repository.save(state)`). Successful application mutations commit **once**;
failed mutations reload workspace state. UI layer code must not scatter
`commit()` calls.

### ADR: Exactly one active secret manager, no silent fallback

One secret provider is active per workspace. The embedded secret manager is the
built-in per-project default and always available; in practice, the external
providers (OpenBao, GCP Secret Manager) are the relevant ones for real
deployments. Unavailable external providers remain selected rather than silently
falling back to embedded storage.

### ADR: Execution abstraction is not "SSH-only"

*Decision:* keep the execution layer (`mlox/execution/base.py`) target-agnostic
even though the only concrete executor today is Fabric/SSH-based
(`UbuntuTaskExecutor`). This is recorded as an ADR because it is an architectural
commitment that is easy to violate accidentally — contributors and agents should
not hard-wire "execution == remote SSH" assumptions. Local and embedded execution
are first-class future targets on the roadmap.

### ADR: Capability metadata is a UI affordance, not yet placement policy

Service capabilities in YAML describe intent and enable UI, but are **not yet**
a complete placement/runtime enforcement model. `requirements` in YAML are
parsed but not enforced at runtime. Planned; see Roadmap.

### ADR: Installation — uv everywhere; Docker delivery removed

**Date:** 2026-09 — **Status:** Accepted
MLOX is installed and developed through [uv](https://docs.astral.sh/uv/) —
deliberately the *only* documented path, because one opinionated option beats
three drifting ones. uv behaves identically on macOS, Linux, and Windows.

- **Users** install the published package: `uv tool install 'busysloths-mlox[tui]'`
  (pipx works equivalently). One command puts `mlox` on PATH; upgrades are
  `uv tool upgrade`. No clone, no environment management.
- **Developers** bootstrap with `task first:steps`, which runs `uv sync` against
  `uv.lock` — reproducible on every OS, no activation needed (commands run via
  `uv run`). Conda is no longer a documented path.
- **Docker delivery is removed** (`Dockerfile`, compose files, DockerHub
  workflow): the image existed to serve the deprecated Streamlit web UI, and a
  container is a poor fit for a client-side CLI/TUI that manages remote
  infrastructure. If an image is ever needed again, rebuild it around the CLI
  from a clean slate.

### ADR: Dependency split — pyproject declares intent, uv.lock pins

**Date:** 2026-09 — **Status:** Accepted
`pyproject.toml` declares dependencies with permissive bounds (names/`>=`
ranges, never `==`); `uv.lock` holds the exact resolved pins for the full
dependency tree, giving developers and CI reproducible environments.

- The lock is **repo-internal**: end-user installs from PyPI resolve fresh from
  pyproject metadata and get only the base dependency set (extras are opt-in).
  The lock is never shipped in the wheel.
- Never hand-edit `uv.lock`. After changing pyproject dependencies, regenerate
  with `task deps:lock` (or use `uv add`/`uv remove`, which update both) and
  commit both files together.
- **CI enforces the link**: `uv lock --check` fails when the lock is out of
  sync with pyproject — the same generate-then-verify pattern used for the
  services catalog.
- Do not pin transitive dependencies in pyproject; that duplicates the lock's
  job in a fragile, consumer-hostile way.

---

## Roadmap

Prioritized open direction (absorbed from the former
`ARCHITECTURE_REFACTOR_PLAN_01.md` and README "planned" markers). This is the
authoritative list.

**How this relates to GitHub issues:** this roadmap is the deliberately
lightweight replacement for a GitHub Projects board — planning truth lives here,
versioned and reviewable with the code. GitHub **issues are derived from roadmap
entries**: when the time comes to work on an item, open an issue for it, link it
back to the entry, and track day-to-day progress there. The roadmap entry stays
the source of truth; the issue is the execution unit. If this ever moves to
GitHub Projects (or another tool), that tool becomes the linked source of truth
and this section must point to it — never duplicate the list in both places.

1. **Project sync (local-first + PostgreSQL snapshot).** MLOX projects remain
   local, encrypted SQLCipher databases. A PostgreSQL instance acts as a sync
   point: a computer publishes the newest state of a project there, and another
   computer working on the same project pulls it and copies it into its local
   SQLCipher DB. Deliberately lightweight — snapshot-based sync of a
   local-first store, not a server-side runtime. (Behind the existing
   data-source boundary: `sqlcipher/self` → optional `postgres` sync target.)
   (Tracked as #92.)
2. **Placement & requirement enforcement.** Verify at setup time that the
   target server actually provides the capabilities a service requires
   (declared in YAML `capabilities`/`requirements`), and enforce them at
   runtime as the model matures. Today they are parsed but not enforced.
3. **Catalog growth.** Deliberately grow the service/connector/server catalog —
   it is the main compounding value of the platform. Candidate integrations:
   1Password or Vault (secret managers), Prometheus + Grafana + Loki
   (observability), Qdrant or Weaviate (vector databases), n8n or Temporal
   (workflow automation), Supabase, ClickHouse, Ray.
4. **Project notes / todo system.** Attach notes and tasks to each MLOX project
   so everything needed to manage the infrastructure for a client lives in one
   place. Natural home: project metadata in the workspace state; surfaced in
   CLI/TUI. (Tracked as #93.)
5. **Agent integration over project state.** An integration that gives an agent
   read access to the current project info (topology, services, secrets
   structure, health) so it can answer questions about the infra — a first step
   toward an agentic MLOps team. Builds directly on the existing
   config-driven topology model.
6. **Tooling/CI baseline.** PR-gated lint + unit tests; adopt a formatter, type
   checker, and pre-commit. Make the Multipass-backed integration tests more
   robust (timeouts, offline resilience) — they are highly valuable but
   currently fail when installs are slow.
7. **Docs governance enforcement.** Keep every surface a derived view via
   `scripts/check_docs.py`.
8. **Multi-project support and RBAC-like access.** Make working with several
   projects practical: suffixed environment variables
   (`MLOX_PROJECT_PATH_<NAME>` / `MLOX_PROJECT_PASSWORD_<NAME>`), a project
   dropdown on the TUI login screen, a runtime project switcher, and
   zero-config discovery of `*.mlox` project files in the current directory
   (tracked as #94). This is also the groundwork for RBAC-like access
   control — per-user/per-role visibility of projects, servers, and services
   once projects are shared across users via [Project
   sync](#project-sync-local-first--postgresql-snapshot) (tracked as #92).

---

## What Changed / Removed

- Feeding docs are consolidated here: former `ARCHITECTURE_REFACTOR_PLAN_01.md`
  (status of the CLI/use-case refactor) has been fully absorbed — its "Still
  Open" items are the first entries in [Roadmap](#roadmap).
- Hand-maintained service/per-version catalogs in README and `wiki/` are replaced
  by the generated `docs/SERVICES_CATALOG.md`.
- Doc consolidation: the five process docs (`GITHUB_PROJECT.md`,
  `PROJECT_PLANNING.md`, `LABELS.md`, `MILESTONE_TEMPLATE.md`,
  `WORKFLOW_QUICK_REFERENCE.md`) merged into `CONTRIBUTING.md`;
  `ARCHITECTURE_AGENTS.md` and the previous agent-notes invariants folded into
  `ARCHITECTURE.md` (now the single entry for humans and agents, with the local
  agent bootstrap file reduced to a thin pointer); `docs/README.md`,
  `website/CONTENT_GUIDE.md`, and the five wiki mirror pages removed;
  out-of-date State-of-the-Union references purged (slides archived in
  `docs/slides/`).
- Install/dependency overhaul: conda-based dev setup replaced by uv
  (`task first:steps` runs `uv sync` against `uv.lock`); Docker delivery
  removed (image served the deprecated Streamlit UI); `pyproject.toml`
  dependencies relaxed from `==` pins to ranges, with `uv.lock` as the pinned
  tree and CI enforcing sync. See the installation and dependency ADRs above.

---

## Document Ownership

| Surface | Location | Rule |
| --------- | ---------- | ------ |
| Doctrine (status/roadmap/decisions) | `docs/DOCTRINE.md` | **Source of truth.** |
| Service/service catalog | `mlox*/**/*.yaml` → `docs/SERVICES_CATALOG.md` | Generated, never hand-edited. |
| Architecture + invariants (humans & agents) | `docs/ARCHITECTURE.md` | Single entry; no status/roadmap. |
| Contributor process | `CONTRIBUTING.md` | Issues, labels, milestones, PRs. |
| Marketing/quickstart | `README.md` | Links only; no catalogs or status lists. |
| GitHub Wiki | `wiki/` | Derived; catalog page is generated. |
| Website | `website/` | Derived; links to doctrine + catalog. |

**Owner:** core maintainer (currently `nicococo`). PRs that change
status/direction must update this file (enforced via the PR template).
