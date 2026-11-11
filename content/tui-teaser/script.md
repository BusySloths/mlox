---
slug: tui-teaser
title: "MLOX in a minute: the terminal UI on real infrastructure"
type: showcase
status: recorded
# One capture name per shot; each becomes content/.work/tui-teaser/captures/<name>.html.
shots:
  - command
  - login
  - overview
  - catalog
  - service
  - monitor
  - models
  - workflow
  - operations
  - knowledge
  - firewall
  - repositories
  - databases
  - cli
# Outputs are listed in content/registry.yaml.
---

# MLOX in a minute: the terminal UI on real infrastructure

A shot list, not a narrated recording. Each shot is one screen held still while
`content/scripts/capture.py` snapshots the pane; there is no narration and no
mouse pointer in the result. Frames are picked and redacted afterwards (see
`docs/CONTENT_PIPELINE.md`, "Terminal captures without screen recording").

## Producing the outputs

The GIF and hero use 174-column crops (the main panel; the login dialog and
the catalog modal centred), the gallery uses full frames.

```sh
W=content/.work/tui-teaser
uv run python -m content.scripts.captures $W/captures.json --frames $W/frames --map $W/redact.json --out $W/captures
uv run python -m content.scripts.stills $W/stills.json --captures $W/captures --work $W/stills
for n in login overview catalog service monitor models workflow; do
  cp $W/captures/teaser_$n.html website/src/captures/teaser/$n.html
done
```

## Where the shots go

| Output | Shots |
| --- | --- |
| README GIF (`tui-demo.gif`, ≤ 15 s, about 2 s per screen) | command (typed), login, overview, catalog, monitor |
| README screenshot (`tui-overview.png`) | overview |
| Website hero teaser (`HeroTeaser.astro`, looping text captures) | login, overview, catalog, service, monitor, models, workflow |
| Website gallery and how-it-works (`mlox_tui_<shot>.png`) | overview, monitor, models, workflow, catalog, service, repositories, databases, firewall, knowledge, cli |

## Setup

- Use a real project with several servers and services deployed. Everything on
  screen is redacted from the text, so nothing is blurred, but keep the set of
  private names small.
- Export the project path and password in the shell beforehand
  (`MLOX_PROJECT_PATH`, `MLOX_PROJECT_PASSWORD`) so the login screen is
  prefilled. Never type the password while capturing.
- Record in one terminal pane and keep its size fixed for the whole session
  (the 2026-11-11 session used 219×61). The CLI shot comes last, in the same
  pane after quitting the TUI.
- Start capture before shot 1:
  `uv run python -m content.scripts.capture --pane <id> --out content/.work/tui-teaser/frames --duration 1800 --interval 2`
- Set the password without echo: `read -s MLOX_PROJECT_PASSWORD; export MLOX_PROJECT_PASSWORD`.
- Hold every shot for at least 4 s so two identical snapshots land on disk.

Never press: **Configure & Add Service**, **Reveal Secret** (Enter on the
Secret Manager tab), service lifecycle buttons, or anything in Project Actions.

## Shot 1 · command

- Blank shell prompt in the TUI pane; type `mlox tui`, do not press Enter yet.
- Hold, then press Enter.
- The typing animation in the GIF is built from this frame by revealing the
  command one character at a time; nothing else is synthesized.

## Shot 2 · login

- The login screen: logo, "Discovered projects", the prefilled project file and
  the masked password.
- Hold, then press **Open**.
- Redact: the project file name and any other discovered project names.

## Shot 3 · overview

- The dashboard after loading, Overview tab active: sidebar with bundles,
  servers and services; the metrics row; the servers table with live state.
- Wait until every server row shows its state before holding.
- Redact: server names, IPs, host names in the sidebar and table.

## Shot 4 · catalog

- Select a server in the sidebar, press **Add Service** in Bundle Actions.
- Hold on the service catalog ("twenty-plus services, one keystroke away").
- Press Esc to close it without adding anything.

## Shot 5 · service

- Select a deployed service in the sidebar (MLflow is a good choice), open the
  **Service** tab: its description, ports, links and state.
- Redact: URLs, ports bound to public addresses, user names.

## Shot 6 · monitor

- **Monitor** tab: CPU, RAM, disk and network per server.
- Hold until the charts have a few data points.

## Shot 7 · models

- **Models** tab: registry, gateway and model versions.
- Do not press `c` (copies a curl example with the endpoint).

## Shot 8 · workflow

- **Workflow** tab: the pipelines and their latest runs.

## Shot 9 · operations

- **Operations (EXPERIMENTAL)** tab, Pipelines view, ideally with a live
  incident from the operator demo (traffic and corruption running).
- If the operator demo is not running, skip this shot; the GIF ends on monitor
  instead and the hero leaves it out.

## Shot 10 · knowledge

- **Knowledge** tab: the project board with a few cards in each column.
- Check the cards for private notes before holding.

## Shot 11 · firewall

- **Firewall** tab: ports opened per service.
- Redact: IPs and source ranges.

## Shot 12 · repositories

- **Repositories** tab: a repository and its file tree.
- Pick a repository that may be shown publicly; redact its owner otherwise.

## Shot 13 · databases

- **Databases** tab: the deployed data stores.

## Shot 14 · cli

- After quitting the TUI with `q`: `mlox --help`, then `mlox server list`.
- Hold on each; the gallery uses the server list.
- Redact: server names and IPs.
