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
| **Web UI** (`mlox ui`) | **Maintained** | The TUI served in the browser via `textual-serve`; same code as the TUI. |
| **Streamlit web UI** (`legacy/ui/`) | **Archived** | Removed from the package; kept outside `mlox/` until deleted. See [Decision ADR](#adr-streamlit-web-ui-extraction). |
| Kubernetes execution | **Stable** | Works well in practice, including Kubernetes-native services. |
| Connector backends | **Beta** | Externally hosted integrations. |
| Native / Docker execution | **Stable** | Primary execution paths. |
| Persistence (SQLCipher `project.mlox`) | **Stable** | Single encrypted file per project. |
| Project sync (PostgreSQL snapshot) | **Planned** | Local-first SQLCipher + optional Postgres sync point; see Roadmap. |
| AI & Operations (Team, Pipelines, Plan) | **Experimental** | Project-scoped workload observation, evidence, planning, and advisory agent workspaces; see Roadmap for boundaries. |

Not every bundled service has a uniform status; maturity labels (Functional /
Beta / Experimental) per component are tracked here as they change, not in the
generated catalog.

---

## Binding Decisions (ADR-lite)

Each entry records a decision and the date it was made. These are conserved
until explicitly reversed here.

### ADR: Streamlit web UI extraction

**Date:** 2026-09, updated 2026-11 — **Status:** Accepted, removal started
The Streamlit web UI is being **removed**. The TUI and CLI are the primary points
of contact for the platform, and the browser is served by the TUI itself.

- **Step 1 (2026-11, done):** `mlox/app.py` and `mlox/view/` moved to
  `legacy/ui/`, outside the package. `mlox/ui/registry.py` no longer loads
  Streamlit handlers; the archived app registers its own. Streamlit
  dependencies left `pyproject.toml` and `uv.lock`.
- `mlox ui` (and `task ui:web`) now serve the Textual TUI in the browser via
  `textual-serve` (in the `tui` extra). It binds to localhost by default; it
  has no login of its own and inherits the shell environment.
- `legacy/ui/` is not installed, linted or tested in CI and gets no changes.
  Its tests run only by hand (`uv run --with streamlit --with
  streamlit-vis-timeline pytest legacy/ui/tests`).
- **Next:** delete `legacy/ui/`, or extract it to a plugin repository if
  someone wants to maintain it.
- Documentation and agents must not describe the Streamlit UI as a maintained
  interface (see `docs/ARCHITECTURE.md`).

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

## Vision & long-term ambitions

- **Ditch the cloud. Your infrastructure. Your rules.** An opinionated platform
  for interconnected services, with AI as a first-class participant and you in
  control of your data, infrastructure, and operational decisions.
- **Grow with the operator.** Start with one person, collaborate as a small team,
  and aspire to enterprise use with stronger governance, isolation, and reliability.

These ambitions guide direction; they are not current capabilities or delivery
commitments. Infrastructure ownership and operational authority stay with you.

---

## Roadmap

- **Planning:** authoritative direction lives here; themes and items have no fixed
  priority order yet. Sequencing will evolve as the product takes shape;
  implementation details live in linked issues or service-local design notes.
- **Issues:** use a theme prefix (e.g. `[Projects & lifecycle]`) and a
  `[ROADMAP_ITEM]` body marker; maintain related issue links here when work changes.
  GitHub owns issue status and acceptance criteria.

### 1. Projects & lifecycle

- **Project sync (local-first + PostgreSQL snapshot).** Publish/pull snapshots
  through PostgreSQL; encrypted SQLCipher stays the local working store.
  - Related issues: [#92](https://github.com/BusySloths/mlox/issues/92).
- **Multi-project support and RBAC-like access.** Add project discovery,
  switching, and named credentials; build toward scoped access for shared projects.
- **Migration & upgrade framework.** Plan and execute service and server
  updates, version upgrades, and migrations with compatibility checks.
  - Include data/configuration migration, backups, post-change verification,
    and rollback or documented recovery when changes cannot be reversed.
- **Project knowledge base.** Shipped; extend with named markdown templates,
  Obsidian import/export, and an agent/LLM chat surface.
  - Related issues: [#100](https://github.com/BusySloths/mlox/issues/100).

### 2. AI & Operations

- **CLI for agents.** Make MLOX usable by external agents through discoverable
  commands, structured output, predictable errors, and non-interactive workflows.
  - Apply scoped access and explicit approval boundaries to infrastructure changes.
- **Agents within MLOX.** Enable agents in the Operations pane to investigate,
  coordinate work, and prepare proposals using project knowledge and live evidence.
  - Develop role runtimes with bounded tools, durable context, and reviewable actions.
- **Service-builder agent.** Develop an agent role that implements requested
  service integrations, configuration, and documentation on demand.
  - Test lifecycle, connectivity, and upgrades in isolated environments; submit
    reviewable changes with test evidence before catalog publication or deployment.
- **Observability & investigation.** Evolve experimental Pipelines and Team
  into reliable multi-source evidence, durable history, and agent investigations.
  - Today: user-started, telemetry-dependent observation and advisory reasoning;
    no scheduler or independent custom-role runtimes.
- **Practical anomaly detection.** Detect meaningful workload and service
  deviations with actionable evidence and a low false-alarm burden.
  - Compare simple statistical baselines with tailored models; measure detection
    quality, alert noise, and resource use on representative operational data.
- **Self-hosted operational models (R&D).** Research and develop task-adapted
  models that run smoothly on ordinary CPUs and modest memory budgets.
  - Explore [BitNet](https://github.com/microsoft/BitNet), compact models, and
    adaptive inference budgets; benchmark suitability before choosing an approach.
- **Controlled remediation.** Build capability-scoped agent access, reviewable
  changes, audit trails, and recovery toward AI-operated infrastructure.
  - Remediation stays explicitly selected and human-approved; autonomous
    free-form infrastructure control remains outside scope.

### 3. Catalog & placement

- **Catalog growth.** Expand services, connectors, and servers across secrets,
  observability, vector databases, workflows, data platforms, and compute.
  - Related issues: [#54](https://github.com/BusySloths/mlox/issues/54),
    [#115](https://github.com/BusySloths/mlox/issues/115).
- **Everyday & personal apps.** Add Memos, Nextcloud, and other everyday apps
  with secure hosting defaults, access controls, private connectivity, and backups.
- **Public marketplace.** Enable discovery, contribution, and installation of
  community-maintained services and integrations.
  - Make provenance, versions, compatibility, permissions, and validation evidence
    visible before installation.
- **Placement & requirement enforcement.** Enforce YAML capabilities and
  requirements at setup, then runtime; currently parsed but unenforced.
- **Model-serving gateway reliability.** Isolate model versions; bound registry
  work, latency, concurrency, overload, and lifecycle behavior.
  - Related issues: [#106](https://github.com/BusySloths/mlox/issues/106),
    [#114](https://github.com/BusySloths/mlox/issues/114).
    Engineering notes: [gateway roadmap](../mlox/services/mlflow_gateway/ROADMAP.md).

### 4. Security & trust

- **Secure interconnectivity.** Connect operators, agents, and services through
  private networks; start with Tailscale and explicit public exposure policies.
  - Explore VPS-to-cloud VPC connectivity for private managed services, with
    scoped routes, access rules, and connectivity checks.
- **Identity & scoped authority.** Give people and agents revocable,
  least-privilege access with approval boundaries and audit trails.
- **Recovery & resilience.** Verify encrypted backups, restoration, and rollback
  of infrastructure and access-policy changes.
- **Security policy and threat model.** Define disclosure procedures and model
  project-file, credential, remote-execution, and future sync trust boundaries.
- **Secrets-handling audit.** Make redaction a tested invariant across logs,
  command output, UI state, and project exports.
- **Release supply-chain hygiene.** Attested publishing is in place; finish
  repository-wide workflow pinning and version-pinned historical API docs.
- **Safe host operations.** Make firewall exposure, Docker policy, bounded logs,
  and partial-setup cleanup recoverable while preserving operator ownership.
  - Related issues: [#110](https://github.com/BusySloths/mlox/issues/110),
    [#111](https://github.com/BusySloths/mlox/issues/111),
    [#112](https://github.com/BusySloths/mlox/issues/112).

### 5. Community & adoption

- **Tutorial / cookbook series.** Publish end-to-end deployment guides as the
  shared source for service recipes and derived demos.
  - Related issues: [#107](https://github.com/BusySloths/mlox/issues/107).
- **Video / demo series.** Maintainer tooling has produced a first README GIF;
  prove recording, alignment, artifact generation, and final-media verification.
  - Related issues: [#108](https://github.com/BusySloths/mlox/issues/108).
- **API documentation quality.** Improve public docstrings, SDK examples,
  navigation, and version-pinned release references.
- **First-run program.** Exercise clean-machine installs and interfaces;
  turn friction into documentation, onboarding, and error-message improvements.
  - Related issues: [#81](https://github.com/BusySloths/mlox/issues/81),
    [#82](https://github.com/BusySloths/mlox/issues/82).
- **Public documentation alignment.** Keep README, website, and wiki aligned
  with current interfaces and product visuals.
  - Related issues: [#91](https://github.com/BusySloths/mlox/issues/91).

### 6. Engineering baseline

- **Tooling/CI baseline.** Gate PRs on lint and unit tests; adopt formatting,
  type checking, and pre-commit.
- **Core abstraction and CLI hardening.** Separate backend runtime behavior;
  unify workspace-open errors and plugin-aware server selection.
  - Related issues: [#77](https://github.com/BusySloths/mlox/issues/77),
    [#102](https://github.com/BusySloths/mlox/issues/102),
    [#103](https://github.com/BusySloths/mlox/issues/103).
- **Test suite depth and robustness.** Extend core coverage and CI reporting;
  broaden integration tests with reliable timeouts, offline handling, and cleanup.
  - Related issues: [#117](https://github.com/BusySloths/mlox/issues/117).
- **Docs governance enforcement.** Keep documentation derived from its sources
  through `scripts/check_docs.py`.

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
| DuckLake setup walkthrough | [docs/DUCKLAKE.md](DUCKLAKE.md) | User-facing setup and first queries; link to the [connector reference](../mlox/services/ducklake/README.md) for service details. |
| Content-production procedure | `docs/CONTENT_PIPELINE.md` | Recipe for script-derived tutorial/demo media; sources live in `content/`. |
| Contributor process | `CONTRIBUTING.md` | Issues, labels, milestones, PRs. |
| Marketing/quickstart | `README.md` | Links only; no catalogs or status lists. |
| GitHub Wiki | `wiki/` | Derived; catalog page is generated. |
| Website | `website/` | Derived; links to doctrine + catalog. |

**Owner:** core maintainer (currently `nicococo`). PRs that change
status/direction must update this file (enforced via the PR template).
