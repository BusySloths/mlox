# GitHub Workflow

This is the lightweight workflow used for MLOX issues, pull requests, labels, and milestones.

## Work Items

Use GitHub Issues for bugs, features, documentation work, and maintenance tasks. Prefer small issues with clear acceptance criteria.

Recommended issue title format:

```text
[component] Short description
```

Examples:

- `[cli] Add service status output`
- `[docs] Refresh installation guide`
- `[services] Fix Redis secret output`

## Labels

Every issue should have:

- one `type:*` label
- one or more `component:*` labels when possible
- a `priority:*` label when triaged
- a `status:*` label while active

See `docs/LABELS.md` for the current label set.

## Pull Requests

Pull requests should:

- link related issues with `Fixes #123` or `Refs #123`
- describe the user-visible change
- mention tests run
- update docs or examples when behavior changes
- keep unrelated refactors out of the PR

Use the repository PR template in `.github/pull_request_template.md`.

## Milestones

Use milestones for release-sized groups of work. Keep milestone descriptions short:

- release goal
- included issues
- release risks or blockers
- test/release checklist

Use `docs/MILESTONE_TEMPLATE.md` when a more structured milestone is useful.

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
