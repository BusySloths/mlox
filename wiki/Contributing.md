# Contributing to MLOX

> **Source:** [`CONTRIBUTING.md`](https://github.com/BusySloths/mlox/blob/main/CONTRIBUTING.md)

---

## Welcome! 👋

Thank you for considering contributing to MLOX. Contributions are not limited to writing code — we welcome:

- 🐛 Bug reports
- 💡 Enhancement suggestions
- 📝 Documentation improvements
- 🧪 Expanding reusable snippets and use-cases

This project is a community effort and won't be possible without your support and enthusiasm.

---

## Where to Start?

Browse the [GitHub Issues tab](https://github.com/BusySloths/mlox/issues) to find something that interests you. MLOX is still in early development — all ideas and improvements are welcome.

---

## Our Workflow

We use a structured approach to manage development:

| Tool | Purpose |
|------|---------|
| **GitHub Projects** | High-level functional areas and epics |
| **Milestones** | Release planning and goal setting |
| **Issues** | Specific features, bugs, and tasks |
| **Labels** | Categorization and prioritization |

### Reference Docs

| Document | Purpose |
|----------|---------|
| [`docs/GITHUB_PROJECT.md`](https://github.com/BusySloths/mlox/blob/main/docs/GITHUB_PROJECT.md) | How we organize work and manage projects |
| [`docs/PROJECT_PLANNING.md`](https://github.com/BusySloths/mlox/blob/main/docs/PROJECT_PLANNING.md) | Creating and managing projects, milestones, and issues |
| [`docs/LABELS.md`](https://github.com/BusySloths/mlox/blob/main/docs/LABELS.md) | Our labeling system for categorizing issues |

---

## Development Environment Setup

See the [Installation](Installation) wiki page for full setup instructions. Quick start:

```bash
git clone https://github.com/BusySloths/mlox.git
cd mlox
task first:steps        # set up conda env 'mlox-dev'
source activate mlox-dev
task ui:streamlit       # launch Web UI
```

Run tests:

```bash
task tests:unit:run
```

---

## Getting Help 🙋

- 🐛 [Open an issue](https://github.com/BusySloths/mlox/issues/new/choose)
- 💬 [Start a discussion](https://github.com/BusySloths/mlox/discussions)
- 📖 [Project Wiki](https://github.com/BusySloths/mlox/wiki)
- 📧 [contact@mlox.org](mailto:contact@mlox.org) or [hello@busysloths.org](mailto:hello@busysloths.org)

---

## See Also

- [Home](Home) — Project overview
- [Installation](Installation) — Setup guide
- [Architecture](Architecture) — Codebase walkthrough
