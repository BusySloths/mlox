# Textual TUI

This package implements the terminal dashboard using Textual.

## Structure

- `app.py`: application lifecycle and project login.
- `screens/login.py`: open and create project flow.
- `screens/dashboard/`: infrastructure tree, details, actions, and logs.
- `services/`: TUI-specific service panels.

The project-level Apps tab groups installed services with the `app` capability
by their mlox proxy, alongside a permanent “No proxy” group. Select a proxy to
see its apps, their recorded state and web UI address. The tab can open an app
and refresh the overview without changing deployed services. The “No proxy”
group means no association with a proxy managed in the current project; it
does not detect external proxies.

## Workflow

Login opens or creates a workspace through `mlox.application` use cases and
stores the returned workspace on the app. Dashboard widgets render the existing
workspace/domain objects, but side-effecting workflows such as reload, template
listing, terminal launch, and service TUI handler resolution go through
`mlox.application`.

## System Role

The TUI is a stateful frontend adapter. Keep deployment logic, persistence,
configuration loading, and external process launches outside widgets and
screens; expose those operations through `mlox.application` use cases.
