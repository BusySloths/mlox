# Contributing to MLOX

> Sources: [`CONTRIBUTING.md`](https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md) · [`docs/WORKFLOW_QUICK_REFERENCE.md`](https://github.com/BusySloths/mlox/blob/main/docs/WORKFLOW_QUICK_REFERENCE.md)

---

## Contents

1. [Ways to Contribute](#ways-to-contribute)
2. [Where to Start](#where-to-start)
3. [Workflow Overview](#workflow-overview)
4. [Labels](#labels)
5. [Issue & PR Checklists](#issue--pr-checklists)
6. [Getting Help](#getting-help)

---

## Ways to Contribute

Thank you for considering contributing to MLOX! Contributions are not limited to code:

- bug reports
- feature ideas
- documentation improvements
- examples and tutorials
- service integrations

MLOX is still early-stage, so clear reports and small focused changes are useful.

---

## Where to Start

1. Browse the [Issues tab](https://github.com/BusySloths/mlox/issues).
2. Filter by `good first issue` for small beginner-friendly tasks.
3. Ask questions in [Discussions](https://github.com/BusySloths/mlox/discussions).
4. Set up your development environment with [Installation](Installation).

---

## Workflow Overview

MLOX uses a lightweight workflow:

```text
idea / bug report
    -> issue with clear outcome
    -> pull request
    -> release note when user-visible
```

Use milestones only when preparing a release. GitHub Projects are not required for
routine planning.

### Development Steps

1. Pick or create a focused issue.
2. Create a branch.
3. Make the change.
4. Run the relevant tests.
5. Open a pull request and link the issue.

---

## Labels

Use labels only when they make the issue list easier to scan or change what a
maintainer does next.

| Label | Meaning |
|-------|---------|
| `type:bug` | Broken behavior |
| `type:feature` | New capability or larger user-visible change |
| `type:documentation` | Docs, examples, or website content |
| `type:maintenance` | Refactoring, dependencies, tests, CI, or cleanup |
| `type:question` | Open usage, design, or product question |
| `priority:urgent` | Security, data loss, broken release, or maintainer-blocking issue |
| `status:blocked` | Waiting on an external dependency or decision |
| `status:needs-info` | Waiting on reporter details before work can start |
| `good first issue` | Small, well-scoped task for a new contributor |
| `help wanted` | External contribution is welcome |

Do not use component, effort, routine status, or special-case labels for now.
Put details such as breaking changes, security context, or dependency risk in the
issue or pull request body.

---

## Issue & PR Checklists

### Creating an Issue

- [ ] Use the most relevant issue template.
- [ ] Write a clear, descriptive title.
- [ ] Include reproduction steps for bugs.
- [ ] Include acceptance criteria for feature or maintenance work.
- [ ] Add one `type:*` label when the type is clear.

### Opening a Pull Request

- [ ] Use the PR template.
- [ ] Link related issues with `Fixes #123` or `Refs #123`.
- [ ] Describe what changed.
- [ ] List tests or manual checks.
- [ ] Update docs/examples when behavior changes.

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| [`docs/GITHUB_PROJECT.md`](https://github.com/BusySloths/mlox/blob/main/docs/GITHUB_PROJECT.md) | GitHub issue, PR, milestone, and release workflow |
| [`docs/PROJECT_PLANNING.md`](https://github.com/BusySloths/mlox/blob/main/docs/PROJECT_PLANNING.md) | Early-stage planning rules |
| [`docs/LABELS.md`](https://github.com/BusySloths/mlox/blob/main/docs/LABELS.md) | Minimal label set and usage |
| [`docs/MILESTONE_TEMPLATE.md`](https://github.com/BusySloths/mlox/blob/main/docs/MILESTONE_TEMPLATE.md) | Optional release milestone template |
| [`docs/WORKFLOW_QUICK_REFERENCE.md`](https://github.com/BusySloths/mlox/blob/main/docs/WORKFLOW_QUICK_REFERENCE.md) | Quick reference and checklists |

---

## Getting Help

- [GitHub Discussions](https://github.com/BusySloths/mlox/discussions)
- [Open an Issue](https://github.com/BusySloths/mlox/issues/new/choose)
- [contact@mlox.org](mailto:contact@mlox.org) or [hello@busysloths.org](mailto:hello@busysloths.org)

---

## See Also

- [Home](Home) - Project overview
- [Architecture](Architecture) - Codebase walkthrough
- [Installation](Installation) - Setup guide
