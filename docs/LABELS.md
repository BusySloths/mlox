# Labels

Use labels only when they make the issue list easier to scan or change what a
maintainer does next. At this stage, the issue title and body should carry most
of the context.

## Default Set

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

## What We Are Not Tracking Yet

Do not use component labels for now. The codebase is still moving quickly, and
areas such as CLI, TUI, services, configuration, and infrastructure can be found
well enough through issue text and linked files.

Do not use effort labels for routine planning. If an issue is too large to
understand, split it or add acceptance criteria instead of estimating it.

Do not use routine status labels such as `needs-triage`, `in-progress`, or
`ready-for-review`. Open issues are the backlog, assignees show active work, and
pull request state shows review readiness.

Do not use special-case labels such as `breaking-change`, `security`, or
`dependencies` for now. Put that context directly in the issue or pull request
body so readers see the details without relying on label taxonomy.

## Triage Rules

- Add exactly one `type:*` label when the type is clear.
- Add `priority:urgent` only when the issue needs immediate maintainer attention.
- Add `status:blocked` or `status:needs-info` only while that state is true.
- Add `good first issue` or `help wanted` only when actively inviting outside
  contribution.
- Prefer editing the issue title/body over adding more labels.
