---
title: "Up and running in three commands"
eyebrow: "Get started"
subtitle: "Slow down. It's already installed."
description: "MLOX is a Python package with a terminal UI included. It runs on macOS, Linux and Windows and talks to your servers over SSH."
steps:
  - title: "Install uv"
    description: "One fast Python package manager for macOS, Linux and Windows."
    code: "curl -LsSf https://astral.sh/uv/install.sh | sh"
    note: "Other platforms and options: <a href=\"https://docs.astral.sh/uv/\" target=\"_blank\" rel=\"noopener noreferrer\">docs.astral.sh/uv</a>"
  - title: "Install MLOX"
    description: "The published package, with the terminal UI included."
    code: "uv tool install 'busysloths-mlox[tui]'"
    note: "Skip the <code>[tui]</code> extra if you only want the CLI."
  - title: "Launch and create a project"
    description: "Start the TUI and press Create on the login screen. MLOX writes your first encrypted, portable project file."
    code: "mlox tui"
    note: "Prefer scripts? <code>mlox --help</code> lists every command."
  - title: "Go deeper"
    description: "Guides for installing, contributing and where MLOX is heading."
    note: >
      Read the <a href="https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md" target="_blank" rel="noopener noreferrer">installation guide</a>,
      the <a href="https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer">contribution guide</a>
      and the <a href="https://github.com/BusySloths/mlox/blob/main/docs/DOCTRINE.md" target="_blank" rel="noopener noreferrer">doctrine</a>.
---
