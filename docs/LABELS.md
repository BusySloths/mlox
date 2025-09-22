# MLOX GitHub Labels Configuration

This file defines the label system for the MLOX repository. Use this as a reference for maintaining consistent labeling across issues and pull requests.

## Type Labels (Required for all issues)

| Label | Color | Description |
|-------|--------|-------------|
| `type:bug` | `#d73a4a` | Something isn't working correctly |
| `type:feature` | `#0075ca` | New functionality or capabilities |
| `type:enhancement` | `#a2eeef` | Improvements to existing features |
| `type:documentation` | `#0052cc` | Documentation changes or additions |
| `type:maintenance` | `#fef2c0` | Code cleanup, refactoring, dependency updates |
| `type:question` | `#d876e3` | Questions about usage or implementation |

## Priority Labels

| Label | Color | Description |
|-------|--------|-------------|
| `priority:critical` | `#b60205` | Critical bugs, security issues, or blocking problems |
| `priority:high` | `#d93f0b` | Important features or significant bugs |
| `priority:medium` | `#fbca04` | Standard priority items |
| `priority:low` | `#0e8a16` | Nice-to-have improvements, minor issues |

## Component Labels

| Label | Color | Description |
|-------|--------|-------------|
| `component:cli` | `#5319e7` | Command line interface related |
| `component:ui` | `#1d76db` | Web user interface related |
| `component:infrastructure` | `#b4a7d6` | Core infrastructure management |
| `component:services` | `#c2e0c6` | Service integrations and management |
| `component:security` | `#d4c5f9` | Security, authentication, secrets management |
| `component:docs` | `#e99695` | Documentation and guides |
| `component:testing` | `#f9d0c4` | Testing infrastructure and test cases |
| `component:ci-cd` | `#c5def5` | Continuous integration and deployment |

## Status Labels

| Label | Color | Description |
|-------|--------|-------------|
| `status:needs-triage` | `#fbca04` | Needs initial review and categorization |
| `status:blocked` | `#b60205` | Blocked by external dependencies or decisions |
| `status:in-progress` | `#0052cc` | Currently being worked on |
| `status:ready-for-review` | `#0e8a16` | Ready for code review |
| `status:waiting-for-feedback` | `#d876e3` | Waiting for feedback from reporter or maintainer |

## Effort Labels (For Planning)

| Label | Color | Description |
|-------|--------|-------------|
| `effort:small` | `#c2e0c6` | 1-2 days of work |
| `effort:medium` | `#bfdadc` | 3-5 days of work |
| `effort:large` | `#f9d0c4` | 1-2 weeks of work |
| `effort:xl` | `#e99695` | More than 2 weeks of work |

## Special Labels

| Label | Color | Description |
|-------|--------|-------------|
| `good-first-issue` | `#7057ff` | Suitable for new contributors |
| `help-wanted` | `#008672` | Community contributions welcome |
| `breaking-change` | `#b60205` | Introduces breaking changes |
| `duplicate` | `#cfd3d7` | Duplicate of another issue |
| `invalid` | `#e4e669` | Invalid issue or doesn't meet criteria |
| `wontfix` | `#ffffff` | Issue will not be fixed or implemented |
| `dependencies` | `#0366d6` | Updates to dependencies |
| `security` | `#d73a4a` | Security-related issues |

## Usage Guidelines

### Applying Labels

1. **Every issue should have at least one type label**
2. **Apply component labels for the affected parts of the system**
3. **Use priority labels to indicate urgency**
4. **Update status labels as work progresses**

### Label Combinations

Examples of well-labeled issues:
- `type:bug`, `component:cli`, `priority:high`, `status:needs-triage`
- `type:feature`, `component:ui`, `priority:medium`, `effort:large`, `help-wanted`
- `type:documentation`, `component:docs`, `priority:low`, `good-first-issue`

### Automation Opportunities

Consider setting up GitHub Actions to:
- Automatically apply `status:needs-triage` to new issues
- Add `component:*` labels based on file paths in PRs
- Update status labels based on PR state changes

## Setting Up Labels

### Method 1: Manual Setup
1. Go to repository Settings → Labels
2. Create each label with the specified name, color, and description
3. Apply labels to existing issues as needed

### Method 2: GitHub CLI (Recommended)
```bash
# Install GitHub CLI first: https://cli.github.com/

# Example commands to create type labels
gh label create "type:bug" --color "d73a4a" --description "Something isn't working correctly"
gh label create "type:feature" --color "0075ca" --description "New functionality or capabilities"
gh label create "type:enhancement" --color "a2eeef" --description "Improvements to existing features"

# Continue for all labels...
```

### Method 3: Label Sync Tools
Use tools like [github-label-sync](https://github.com/Financial-Times/github-label-sync) with a configuration file.

## Maintenance

### Regular Review
- Monthly review of label usage and effectiveness
- Archive or rename labels that are no longer useful
- Add new labels as the project evolves

### Community Feedback
- Ask contributors about label clarity and usefulness
- Adjust based on actual usage patterns
- Update documentation when labels change

## Best Practices

1. **Be Consistent**: Use the same labeling patterns across all issues
2. **Be Specific**: Use multiple labels to provide clear context
3. **Be Timely**: Apply labels when creating or reviewing issues
4. **Be Helpful**: Labels should help contributors find relevant work

## Examples

### Well-Labeled Issues

**Example 1: Bug Report**
```
Title: [CLI] Service status command fails with timeout error
Labels: type:bug, component:cli, component:services, priority:high, status:needs-triage
```

**Example 2: Feature Request**
```
Title: [UI] Add dark mode support to web interface
Labels: type:feature, component:ui, priority:medium, effort:medium, help-wanted
```

**Example 3: Documentation**
```
Title: [DOCS] Create tutorial for setting up Docker services
Labels: type:documentation, component:docs, component:services, priority:low, good-first-issue
```

This labeling system helps maintain organization and makes it easier for contributors to find issues that match their interests and expertise level.