# GitHub Workflow

This is the early-stage workflow used for MLOX issues, pull requests, labels, and
milestones.

## Work Items

Use GitHub Issues for bugs, features, documentation work, and maintenance tasks.
Prefer small issues with a clear outcome.

Recommended issue title format:

```text
[area] Short description
```

Examples:

- `[cli] Add service status output`
- `[docs] Refresh installation guide`
- `[redis] Fix secret output`

The area in brackets is plain title text, not a required label.

## Labels

Every issue may have:

- one `type:*` label when the type is clear
- `priority:urgent` only for immediate maintainer attention
- `status:blocked` or `status:needs-info` only while true
- `good first issue` or `help wanted` when actively inviting outside contribution

Do not require component, effort, or routine status labels. See `docs/LABELS.md`
for the current label set.

## Pull Requests

Pull requests should:

- link related issues with `Fixes #123` or `Refs #123`
- describe the user-visible change
- mention tests run
- update docs or examples when behavior changes
- keep unrelated refactors out of the PR

Use the repository PR template in `.github/pull_request_template.md`.

## Milestones

Use milestones only for release-sized groups of work. Keep milestone descriptions
short:

- release goal
- required issues
- release risks or blockers
- tests and docs that matter for this release
- deferred work

Use `docs/MILESTONE_TEMPLATE.md` when a structured milestone is useful.

## Branches And Commits

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

## Release Notes

For user-visible changes, capture:

- new features
- fixed bugs
- changed behavior
- migration notes
- known limitations

Release automation and publication workflows live in `.github/workflows/`.

## Contributor Entry Points

- Issues: <https://github.com/BusySloths/mlox/issues>
- Discussions: <https://github.com/BusySloths/mlox/discussions>
- Source: <https://github.com/BusySloths/mlox>
- Contact: `contact@mlox.org`
