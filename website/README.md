# MLOX Landing Page

This is the landing page for the MLOX project, built with Astro.

## 🚀 Project Structure

```
website/
├── public/           # Static assets
├── src/
│   ├── content/pages/# Page copy in Markdown with YAML frontmatter (hero, features, getting-started)
│   ├── layouts/     # Layout components
│   ├── pages/       # Page components
│   └── components/  # Reusable components
├── astro.config.mjs # Astro configuration
├── package.json     # Dependencies
└── tsconfig.json    # TypeScript configuration
```

## 📝 Updating Content

To update the landing page copy, edit the Markdown files in `src/content/pages/`.
Each file has frontmatter (metadata between `---`) and content below:

- **hero.md** - Hero headline, install command, CTAs and the stats strip
- **gallery.md** - "Explore the TUI" tabs: one entry per screenshot (`image` is the basename in `public/`, served as `.webp` with a `.png` fallback)
- **features.md** - Feature panels and the service marquee (`services`)
- **how-it-works.md** - The three illustrated steps
- **why-mlox.md** - "Why MLOX" cards; the body of `hero.md` is shown as their intro
- **getting-started.md** - Install steps with copyable commands

Screenshots and the hero video (`public/mlox_tui_*`) come from the content
pipeline (`content/registry.yaml`, piece `website-tui`): they are recorded from a
real project and redacted before they land here. See `docs/CONTENT_PIPELINE.md`.

## 🧞 Commands

All commands are run from the `website` directory:

| Command                   | Action                                           |
| :------------------------ | :----------------------------------------------- |
| `npm install`             | Installs dependencies                            |
| `npm run dev`             | Starts local dev server at `localhost:4321`      |
| `npm run build`           | Build your production site to `./dist/`          |
| `npm run preview`         | Preview your build locally, before deploying     |
| `npm run astro ...`       | Run CLI commands like `astro add`, `astro check` |

## 🚀 Deployment

The site is deployed to GitHub Pages by
`.github/workflows/deploy-docs.yml`, either manually, for a manually published
GitHub Release, or as part of the **Deploy Release** workflow. API docs are
mounted under `/docs/`, and release deployments inject a link to the released
version into the site header.

The site will be available at: `https://busysloths.github.io/mlox/`

## 📦 Technologies

- **Astro** - Static site generator
- **TypeScript** - Type-safe JavaScript
- **Markdown** - Content management

## 📄 License

MIT License - see the [LICENSE](../LICENSE) file for details.
