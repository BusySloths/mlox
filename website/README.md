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

- **hero.md** - Main hero section with tagline and CTA buttons
- **features.md** - Features showcase section
- **getting-started.md** - Quick start guide section

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

The site is automatically deployed to GitHub Pages when changes are pushed to the main branch via the GitHub Actions workflow at `.github/workflows/deploy-website.yml`.

The site will be available at: `https://busysloths.github.io/mlox/`

## 📦 Technologies

- **Astro** - Static site generator
- **TypeScript** - Type-safe JavaScript
- **Markdown** - Content management

## 📄 License

MIT License - see the [LICENSE](../LICENSE) file for details.
