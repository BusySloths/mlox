# Labels

Use labels to make issues and pull requests searchable. Keep the set small and predictable.

## Type

Every issue should have one type label.

| Label | Use |
| --- | --- |
| `type:bug` | Broken behavior |
| `type:feature` | New functionality |
| `type:enhancement` | Improvement to existing behavior |
| `type:documentation` | Docs or examples |
| `type:maintenance` | Refactoring, dependencies, cleanup |
| `type:question` | Usage or design question |

## Priority

| Label | Use |
| --- | --- |
| `priority:critical` | Security, data loss, or release blocker |
| `priority:high` | Important and time-sensitive |
| `priority:medium` | Normal priority |
| `priority:low` | Nice to have |

## Component

| Label | Use |
| --- | --- |
| `component:cli` | CLI commands and output |
| `component:tui` | Textual terminal UI |
| `component:ui` | Streamlit web UI |
| `component:infrastructure` | Session, infra, servers, executors |
| `component:services` | Built-in service integrations |
| `component:config` | YAML config loading and plugins |
| `component:security` | Secrets, credentials, auth |
| `component:docs` | Documentation |
| `component:testing` | Tests and fixtures |
| `component:ci-cd` | GitHub Actions and release workflows |

## Status

| Label | Use |
| --- | --- |
| `status:needs-triage` | Not reviewed yet |
| `status:blocked` | Waiting on a dependency or decision |
| `status:in-progress` | Someone is actively working on it |
| `status:ready-for-review` | Ready for review |
| `status:waiting-for-feedback` | Waiting on reporter or contributor |

## Effort

Use effort labels only when they help planning.

| Label | Use |
| --- | --- |
| `effort:small` | About 1-2 days |
| `effort:medium` | About 3-5 days |
| `effort:large` | About 1-2 weeks |
| `effort:xl` | Larger than 2 weeks; consider splitting |

## Special

| Label | Use |
| --- | --- |
| `good-first-issue` | Good for new contributors |
| `help-wanted` | External help welcome |
| `breaking-change` | Changes public behavior or compatibility |
| `dependencies` | Dependency update |
| `security` | Security-sensitive issue |
| `duplicate` | Duplicate issue |
| `invalid` | Not actionable or out of scope |
| `wontfix` | Intentionally not planned |

## Guidelines

- Add at least one type label to every issue.
- Add component labels for affected areas.
- Add priority only after triage.
- Keep status labels current while work is active.
- Split issues labeled `effort:xl` where possible.
