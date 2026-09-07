---
title: "Get Started"
subtitle: "Sloth-Friendly Setup"
description: "Easing into MLOX should feel like a lazy stretch on a sunny branch"
steps:
  - title: "Install uv"
    description: "One installer for macOS, Linux, and Windows"
    code: "curl -LsSf https://astral.sh/uv/install.sh | sh"
    note: "uv is a fast Python package manager — see <a href=\"https://docs.astral.sh/uv/\" target=\"_blank\" rel=\"noopener noreferrer\" class=\"text-accent-cyan hover:text-accent-purple underline font-semibold\">docs.astral.sh/uv</a> for other platforms"
  - title: "Install MLOX"
    description: "Get the published package with the terminal UI included"
    code: "uv tool install 'busysloths-mlox[tui]'"
    note: "The [tui] extra pulls in the terminal UI; without it you get the CLI only"
  - title: "Launch and Create a Project"
    description: "Start the TUI and hit the Create button on the login screen"
    code: "mlox tui"
    note: "That's it — MLOX makes your first encrypted, portable project file for you. Prefer the CLI? Run mlox --help to explore every command"
  - title: "Want the Big Picture?"
    description: "Check out our comprehensive guides"
    note: >
      For a more detailed guide, check out our
      <a href="https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md" target="_blank" rel="noopener noreferrer" class="text-accent-cyan hover:text-accent-purple underline font-semibold">Installation Guide</a>.
      Want to contribute instead? The
      <a href="https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer" class="text-accent-cyan hover:text-accent-purple underline font-semibold">Contribution Guide</a>
      shows how to set up a development environment. For status and direction, see the
      <a href="https://github.com/BusySloths/mlox/blob/main/docs/DOCTRINE.md" target="_blank" rel="noopener noreferrer" class="text-accent-cyan hover:text-accent-purple underline font-semibold">Doctrine</a>
---
