# MLOX Doctrine

> **The single point of truth for MLOX status, roadmap, and binding decisions.**
> Every other document — README, `docs/ARCHITECTURE_*.md`, `CLAUDE.md`, the
> website, and the wiki — is a *view*: it may summarize and link here, but it must
> **not restate** facts. When you change status, roadmap, or a core decision,
> change it here first.

**Documentation rule:** *one fact = one home. Everything else links or is
generated.* Facts about the service/server catalog are generated from the YAML
configs (`docs/SERVICES_CATALOG.md`); status, roadmap, and decisions live here;
architecture lives in `docs/ARCHITECTURE_*.md`; everything else derives.

---

## Component Status

| Component | Status | Notes |
|-----------|--------|-------|
| **CLI** (`mlox/cli/`) | **Primary interface** | Maintained, fully supported. |
| **TUI** (`mlox/tui/`) | **Primary interface** | Maintained, fully supported. |
| **Web UI / Streamlit** (`mlox/view/`, `mlox/app.py`) | **Deprecated** | Will be extracted to a plugin repo. See [Decision ADR](#adr-streamlit-web-ui-extraction). No new features or investments. |
| Kubernetes execution | **Experimental** | Declared supported; expect churn. |
| Connector backends | **Beta** | Externally hosted integrations. |
| Native / Docker execution | **Stable** | Primary execution paths. |
| Persistence (SQLCipher `project.mlox`) | **Stable** | Single encrypted file per project. |
| PostgreSQL repository | **Planned** | Behind the existing data-source boundary; see Roadmap. |

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
  interface going forward (see `CLAUDE.md`).

### ADR: SQLModel deferred
Deliberately not introducing SQLModel ORM records yet. The infrastructure graph
remains behavior-heavy and polymorphic; the JSON snapshot is authoritative.
Reconsider when partial queries, concurrent updates, or PostgreSQL become active
requirements.

### ADR: One transaction for metadata + infrastructure
Metadata and infrastructure are persisted atomically in one transaction.
Successful application mutations commit **once**; failed mutations reload
workspace state. UI layer code must not scatter `commit()` calls.

### ADR: Exactly one active secret manager, no silent fallback
One secret provider is active per workspace. Unavailable external providers
remain selected rather than silently falling back to embedded storage.

### ADR: Execution abstraction is not "SSH-only"
The execution layer (`mlox/execution/base.py`) is target-agnostic by design.
The current concrete `UbuntuTaskExecutor` is Fabric/SSH-based, but local and
embedded execution are first-class on the roadmap. Do not assume
"execution == remote SSH".

### ADR: Capability metadata is a UI affordance, not yet placement policy
Service capabilities in YAML describe intent and enable UI, but are **not yet**
a complete placement/runtime enforcement model. `requirements` in YAML are
parsed but not enforced at runtime. Planned; see Roadmap.

---

## Roadmap

Prioritized open direction (absorbed from the former
`ARCHITECTURE_REFACTOR_PLAN_01.md` and README "planned" markers). This is the
authoritative list.

1. **PostgreSQL repository** support behind the existing data-source boundary
   (`sqlcipher/self` → `postgres`).
2. **Placement model**: move service capability metadata toward a real placement
   policy; enforce `requirements` at runtime.
3. **Growth**: sustain and validate the plugin catalog as the value
   compounding mechanism.
4. **Tooling/CI baseline**: PR-gated lint + unit tests; adopt a formatter, type
   checker, and pre-commit.
5. **Docs governance enforcement**: keep every surface a derived view via
   `scripts/check_docs.py`.

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
  `ARCHITECTURE_AGENTS.md` merged into `CLAUDE.md`; `ARCHITECTURE_HUMANS.md`
  renamed to `ARCHITECTURE.md`; `docs/README.md`, `website/CONTENT_GUIDE.md`,
  and the five wiki mirror pages removed; out-of-date State-of-the-Union
  references purged (slides archived in `docs/slides/`).

---

## Document Ownership

| Surface | Location | Rule |
|---------|----------|------|
| Doctrine (status/roadmap/decisions) | `docs/DOCTRINE.md` | **Source of truth.** |
| Service/service catalog | `mlox*/**/*.yaml` → `docs/SERVICES_CATALOG.md` | Generated, never hand-edited. |
| Architecture (humans) | `docs/ARCHITECTURE.md` | Pure architecture; no status/roadmap. |
| Agent invariants | `CLAUDE.md` | Agent interpretation + code invariants; no volatile stats. |
| Contributor process | `CONTRIBUTING.md` | Issues, labels, milestones, PRs. |
| Marketing/quickstart | `README.md` | Links only; no catalogs or status lists. |
| GitHub Wiki | `wiki/` | Derived; catalog page is generated. |
| Website | `website/` | Derived; links to doctrine + catalog. |

**Owner:** core maintainer (currently `nicococo`). PRs that change
status/direction must update this file (enforced via the PR template).
