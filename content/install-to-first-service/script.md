---
slug: install-to-first-service
title: Install MLOX, open the TUI, deploy your first service
type: tutorial
status: draft
chapters:
  - intro
  - install
  - first-run
  - tui-tour
  - first-service
  - wrap-up
---

# Install MLOX, open the TUI, deploy your first service

> Narration cues are blockquotes; on-screen steps are bullets. Every chapter
> starts with a spoken `chapter: <name>` marker.

## Chapter: intro

> What viewers will learn and for whom.

- What MLOX is in one sentence
- What we will have at the end: one server, one deployed service, TUI-managed

## Chapter: install

> Show the one-liner; mention uv and Python 3.11–3.12.

- Install uv (curl one-liner on screen)
- `uv tool install mlox[tui]`
- Verify: `mlox --version`

## Chapter: first-run

> Clean directory, encrypted project file created on first open.

- `mkdir demo && cd demo`
- Start the TUI, pick a project name and password
- Point out the created `<project>.mlox` file

## Chapter: tui-tour

> Quick tour so viewers can orient themselves in later chapters.

- Dashboard areas: sidebar tree, tabs, status bar
- Add the first server (template form walkthrough)
- Knowledge tab: board + entries in 30 seconds

## Chapter: first-service

> The payoff: a real service running on the new server.

- Pick a service template (e.g. MLflow tracking)
- Fill the form, deploy, watch it come up
- Open the service web UI

## Chapter: wrap-up

> Recap and pointers.

- What was done, where to go next (docs, repo, more recipes)
