# Project Planning

MLOX is still early-stage, so planning should optimize for clarity and momentum
instead of portfolio management. Use issues as the backlog, pull requests as the
review unit, and milestones only when preparing a release.

## Current Process

```text
idea / bug report
    -> issue with clear outcome
    -> pull request
    -> release note when user-visible
```

Add a milestone only when work is intended to ship together in the next release.
Do not require GitHub Projects for routine planning.

## Issue Triage

For each new issue:

1. Make the title and first comment understandable without extra labels.
2. Add one `type:*` label when the type is clear.
3. Ask for reproduction steps, logs, or acceptance criteria when needed.
4. Mark only exceptional state with `priority:urgent`, `status:blocked`, or
   `status:needs-info`.

Good issues include:

- the problem or desired outcome
- reproduction steps for bugs
- the command, service, or interface involved
- the smallest useful acceptance criteria

Avoid component labels for now. The repository is small enough that text search,
linked files, and issue descriptions are more useful than maintaining a component
taxonomy.

## Milestones

Use milestones for near-term releases, not as a standing planning board. A useful
milestone answers:

- What should this release accomplish?
- Which issues must be done before release?
- Which tests or docs matter for the release?
- What is explicitly deferred?

Use `docs/MILESTONE_TEMPLATE.md` only for larger releases. Small releases can use
a short paragraph and an issue list.

## Pull Request Review

Review for:

- correctness and regressions
- CLI/TUI/user-visible behavior drift
- persistence, secrets, service, and infrastructure impact
- tests for changed behavior
- docs/examples when behavior changes

Prefer small PRs. If a PR mixes architecture, UI, docs, and unrelated cleanup,
ask for a narrower scope.

## Release Checklist

Before a release:

- release-blocking issues are resolved or explicitly deferred
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
