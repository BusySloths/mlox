# Project Planning

MLOX planning should stay simple: issues track work, milestones group release goals, and pull requests implement changes.

## Planning Flow

```text
idea / bug report
    -> issue
    -> milestone when release-relevant
    -> pull request
    -> release notes when user-visible
```

## Issue Triage

For each new issue:

1. Confirm the problem or goal is understandable.
2. Add a `type:*` label.
3. Add relevant `component:*` labels.
4. Add `priority:*` after triage.
5. Add `status:needs-triage`, `status:blocked`, or `status:in-progress` as appropriate.
6. Ask for missing reproduction details or acceptance criteria when needed.

Good issues include:

- expected behavior
- actual behavior or requested outcome
- reproduction steps for bugs
- affected interface or service
- acceptance criteria for features

## Milestones

Use milestones for work that should ship together. Avoid turning milestones into full project plans; they should answer:

- What are we trying to release?
- Which issues are included?
- What must be tested?
- What is blocked?

Use `docs/MILESTONE_TEMPLATE.md` for larger releases.

## Pull Request Review

Review for:

- correctness and regressions
- config/session/infra persistence impact
- executor boundary violations
- CLI/TUI/Streamlit behavior drift
- tests and docs for user-visible behavior

Prefer small PRs. If a PR mixes architecture, UI, docs, and unrelated cleanup, ask for a narrower scope.

## Release Checklist

Before a release:

- milestone issues are resolved or explicitly deferred
- unit tests pass
- integration tests are run when infrastructure behavior changed
- docs/examples reflect user-visible changes
- release notes mention breaking changes and migration steps
- package/Docker publishing workflows are green

## Useful References

- Labels: `docs/LABELS.md`
- Milestone template: `docs/MILESTONE_TEMPLATE.md`
- GitHub workflow summary: `docs/GITHUB_PROJECT.md`
- Installation: `docs/INSTALLATION.md`
