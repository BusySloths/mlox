# Workflow Quick Reference

## For Contributors

1. Read `CONTRIBUTING.md`.
2. Install locally with `docs/INSTALLATION.md`.
3. Pick or create an issue.
4. Keep the change focused.
5. Open a PR and list the tests you ran.

## For Maintainers

1. Triage new issues with labels from `docs/LABELS.md`.
2. Keep milestones small and release-focused.
3. Review PRs for regressions, tests, and docs.
4. Update release notes for user-visible changes.

## Common Commands

```bash
task
task first:steps
task tests:unit:run
task tests:integration:run
task docker:up
task docker:down
task ui:streamlit
task ui:cli
task ui:textual:terminal
```

## Issue Checklist

- clear title
- expected outcome
- reproduction steps for bugs
- acceptance criteria for features
- `type:*` label
- relevant `component:*` labels
- priority/status after triage

## Pull Request Checklist

- links related issue
- explains what changed
- documents tests run
- updates docs/examples when behavior changed
- avoids unrelated cleanup

## References

- GitHub workflow: `docs/GITHUB_PROJECT.md`
- Project planning: `docs/PROJECT_PLANNING.md`
- Labels: `docs/LABELS.md`
- Milestone template: `docs/MILESTONE_TEMPLATE.md`
