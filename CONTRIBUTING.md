# How to Contribute

Hello :wave: Thank you for considering contributing to MLOX. There are many ways
to contribute beyond writing code: bug reports, enhancement suggestions, docs
improvements, and reusable snippets and examples.

This is a community effort and wouldn't be possible without support and
enthusiasm.

> **Note on status/decisions:** MLOX is young and evolving fast — the software
> does not yet prescribe a rigid process. The lightweight workflow below is what
> we actually use; if it stops matching reality, change it here.
>
> - Product **status, roadmap, and decisions** live in `docs/DOCTRINE.md` — update
>   that file if your change affects them.
> - The service/server catalog is generated (`docs/SERVICES_CATALOG.md`); never
>   hand-edit it.
> - The Streamlit web UI (`mlox/view/` and `mlox/app.py`) is deprecated and moving
>   to a plugin repo; PRs there are maintenance-only.

## Where to Start

New to open-source? Browse the [issues tab](https://github.com/busysloths/mlox/issues)
for something that interests you, then set up your dev environment:

1. Follow `docs/INSTALLATION.md` to install and run MLOX.
2. Pick or create a focused issue.
3. Open a PR and list the tests you ran.

## How We Work

Planning is deliberately lightweight — the issue list is the backlog, pull
requests are the review unit, and milestones appear only when preparing a release.
There is **no GitHub Projects board**; don't require it for routine planning.

```text
idea / bug report
    -> issue with a clear outcome
    -> pull request
    -> release note when user-visible
```

## Issues & Triage

Use GitHub Issues for bugs, features, docs work, and maintenance tasks. Prefer
small issues with a clear outcome. A good issue is understandable on its own —
title and body carry the context, labels stay minimal.

Recommended issue title format (the `[area]` is plain title text, not a label):

```text
[cli] Add service status output
[docs] Refresh installation guide
[redis] Fix secret output
```

Good issues include: the problem or desired outcome, reproduction steps for bugs,
the command/service/interface involved, and the smallest useful acceptance criteria.

For each new issue:

1. Make the title and first comment understandable without extra labels.
2. Add **one** `type:*` label when the type is clear.
3. Ask for reproduction steps, logs, or acceptance criteria when needed.
4. Mark only exceptional state with `priority:urgent`, `status:blocked`, or
   `status:needs-info`.

## Labels

Use labels only when they make the issue list easier to scan or change what a
maintainer does next. Prefer editing the issue title/body over adding more labels.

| Label | Use |
| --- | --- |
| `type:bug` | Broken behavior |
| `type:feature` | New capability or larger user-visible change |
| `type:documentation` | Docs, examples, or website content |
| `type:maintenance` | Refactoring, dependencies, tests, CI, cleanup |
| `type:question` | Open usage, design, or product question |
| `priority:urgent` | Security, data loss, broken release, or maintainer-blocking issue |
| `status:blocked` | Waiting on an external dependency or decision |
| `status:needs-info` | Waiting on reporter details before work can start |
| `good first issue` | Small, well-scoped task for a new contributor |
| `help wanted` | External contribution is welcome |

**What we are not tracking yet:**

- **No component labels** — the codebase moves too fast; search text, linked
  files, and descriptions are more useful than a component taxonomy.
- **No effort labels** — if an issue is too large to understand, split it or add
  acceptance criteria instead of estimating.
- **No routine status labels** (`needs-triage`, `in-progress`,
  `ready-for-review`) — open issues are the backlog, assignees show active work,
  PR state shows review readiness.
- **No special-case labels** (`breaking-change`, `security`, `dependencies`) —
  put that context in the issue or PR body.

## Pull Requests

Authors should:

- link related issues with `Fixes #123` or `Refs #123`
- describe the user-visible change
- list the tests they ran
- update docs or examples when behavior changes
- keep unrelated refactors out of the PR
- use the repo PR template (`.github/pull_request_template.md`)

Reviewers check for:

- correctness and regressions
- CLI/TUI and other user-visible behavior drift
- persistence, secrets, service, and infrastructure impact
- tests for changed behavior
- docs/examples when behavior changes

Prefer small PRs. If a PR mixes architecture, UI, docs, and unrelated cleanup,
ask for a narrower scope.

### Branches And Commits

Branch names should be descriptive:

```text
feature/123-service-status
fix/456-redis-secret
docs/installation-refresh
```

Commit messages should explain the change and can reference issues:

```text
feat: add service status command
fix: preserve Redis password during reload
docs: refresh installation guide
```

## Milestones & Releases

Use milestones only for release-sized groups of work — not as a standing planning
board. A useful milestone answers: what should this release accomplish, which
issues must be done before release, which tests/docs matter, and what is deferred.

Before a release:

- release-blocking issues are resolved or explicitly deferred
- unit tests pass
- integration tests are run when infrastructure behavior changed
- docs/examples reflect user-visible changes
- release notes mention breaking changes and migration steps
- package/Docker publishing workflows are green

Release notes should capture new features, fixed bugs, changed behavior, migration
notes, and known limitations.

For a structured milestone description, use the template below (skip for small
releases):

````markdown
# v0.x.0 - Release Name

## Goal

Short description of what this release should accomplish.

## Required Work

- [ ] #123 Feature or fix
- [ ] #124 Documentation or migration task

## Before Release

- [ ] Unit tests pass
- [ ] Integration tests run if infrastructure behavior changed
- [ ] User-visible behavior is documented
- [ ] Breaking changes have migration notes
- [ ] Release notes are ready

## Deferred

- #125 Follow-up that does not block this release

## Risks / Blockers

- Risk or blocker
````

## Common Commands

```bash
task
task first:steps
task dev:lint                 # flake8
task tests:unit:run
task tests:integration:run    # requires Multipass VMs
task tests:integration:k8s    # Kubernetes integration (requires Multipass/k3s)
task docker:up
task docker:down
task ui:cli CLI_ARGS="--help"
task ui:textual:terminal
```

## Getting Help

<a href="https://github.com/BusySloths/mlox/issues">
<img alt="GitHub Issues or Pull Requests" src="https://img.shields.io/github/issues/busysloths/mlox">
</a>
<a href="https://github.com/BusySloths/mlox/discussions">
<img alt="GitHub Discussions" src="https://img.shields.io/github/discussions/busysloths/mlox">
</a>

If you have problems, contact a maintainer or community volunteer. The GitHub
issues are a great place to start.

Questions: `contact[at]mlox.org` or `hello[at]busysloths.org`.
