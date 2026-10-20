---
slug: pilot-demo
title: "MLOX in two minutes: from command line to your infrastructure"
type: demo
status: draft
chapters:
  - command-line
  - load-project
  - main-screen
  - navigate-tabs
outputs:
  - type: readme_gif
    dest: mlox/resources/tui-demo.gif
  - type: screenshot
    dest: mlox/resources/tui-login.png
  - type: screenshot
    dest: mlox/resources/tui-overview.png
  - type: screenshot
    dest: mlox/resources/tui-tabs.png
---

# MLOX in two minutes: from command line to your infrastructure

> Narration cues are blockquotes (speak them); on-screen steps are bullets
> (do them). Start each chapter with a spoken `chapter: <name>` marker.

## Chapter: command-line

> "MLOX runs in your terminal — one command starts the terminal UI."

- Start on a blank command line
- Type `mlox tui` and press enter
- The MLOX splash/login screen appears

## Chapter: load-project

> "Projects are single encrypted files — pick one, enter the password, open."

- The login screen shows discovered projects in the dropdown
- Select your project, enter the password
- Press **Open**

## Chapter: main-screen

> "This is home base: your infrastructure at a glance."

- Sidebar: bundles, servers, and every deployed service
- Metrics row: bundles, services, CPU cores, RAM
- Servers table: live state per server
- Project actions below

## Chapter: navigate-tabs

> "Everything is managed through these tabs — no web consoles, no SSH."

- Click through: Models (registries, endpoints, serving)
- Monitor (CPU/RAM/disk/network per service)
- Repositories (code repositories, file browser)
- Knowledge (project notes, todos, and boards)
