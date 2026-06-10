# Content Management Guide

This guide explains how to update the content on the MLOX landing page.

## Content Structure

The main landing-page copy is stored under `src/content/pages/` and rendered by `src/pages/index.astro`. Layout-specific labels, screenshots, sponsors, and the footer remain in `index.astro`.

## How to Update Content

### 1. Hero Section

Edit `/website/src/content/pages/hero.md`:

```yaml
---
title: "Deploy and manage ML/AI infrastructure on your own servers."
subtitle: "Slothfully simple."
description: "Servers, Docker, Kubernetes, databases, workflows, model serving, data services, tracking, and monitoring, with your product at the center. Managed in one place and connected by design."
cta_primary: "Get Started"
cta_primary_link: "https://github.com/BusySloths/mlox"
cta_secondary: "View Documentation"
cta_secondary_link: "https://github.com/BusySloths/mlox/blob/main/docs/INSTALLATION.md"
---
```

**Fields:**
- `title` - Main heading
- `subtitle` - Subheading below the title
- `description` - Supporting line shown in the hero and used as page metadata
- `cta_primary` - Text for primary call-to-action button
- `cta_primary_link` - URL for primary button
- `cta_secondary` - Text for secondary button
- `cta_secondary_link` - URL for secondary button

Markdown below the frontmatter is rendered in the product overview section.

### 2. Features Section

Edit `src/content/pages/features.md`. Each feature has a title, text icon, color, optional description, and list of items.

### 3. Getting Started Section

Edit `src/content/pages/getting-started.md` to modify:

- section title, subtitle, and description
- setup steps and commands
- notes and documentation links

Edit `src/content/pages/why-mlox.md` for the reason cards.

### 4. Sponsors and Supporters

To update sponsor logos:

1. Find the `<!-- Sponsors Section -->`
2. Update the image URLs in the `<img>` tags
3. Add new logos by adding more `<img>` tags

Current logos are referenced from the GitHub repository:
```html
<img 
  src="https://github.com/BusySloths/mlox/blob/main/mlox/resources/BMFTR_logo.jpg?raw=true" 
  alt="BMFTR" 
  class="sponsor-logo"
/>
```

### 5. Footer Content

The footer is at the bottom of `index.astro` in the `<!-- Footer -->` section. Update:

- Company description
- Links to documentation
- Contact email
- Copyright year

## Styling

All styling is included in the `<style>` section at the bottom of `index.astro`. To change colors, fonts, or layout:

1. Locate the `:root` CSS variables at the top of the style section
2. Modify colors, fonts, and spacing
3. For more complex changes, edit the CSS classes

Example CSS variables:
```css
:root {
  --color-primary: #2563eb;
  --color-primary-dark: #1e40af;
  --color-secondary: #10b981;
  /* ... */
}
```

## Markdown Reference Files

The files in `src/content/` are kept as reference/documentation but are not directly used by the build process. You can refer to them when updating content in `index.astro`, but changes to these markdown files won't affect the live site.

To make these files functional (if needed in the future), you would need to:
1. Use Astro's Content Collections feature
2. Or implement a build-time markdown parser

## Testing Changes

After making changes:

1. Run the development server:
   ```bash
   cd website
   npm run dev
   ```

2. Open your browser to `http://localhost:4321`

3. Verify your changes look correct

4. Build for production:
   ```bash
   npm run build
   ```

5. Preview the production build:
   ```bash
   npm run preview
   ```

## Deployment

Once you commit and push changes to the `main` branch, GitHub Actions will automatically:
1. Build the site
2. Deploy it to GitHub Pages
3. Make it available at `https://busysloths.github.io/mlox/`

## Tips

- **Keep it simple**: The landing page is designed to be a single page
- **Test locally**: Always test your changes locally before pushing
- **Mobile-friendly**: The design is responsive, but test on mobile devices
- **Image optimization**: Keep images reasonably sized for fast loading
- **External links**: Use `target="_blank" rel="noopener noreferrer"` for external links

## Need Help?

If you have questions or need assistance with content updates:
- Open an issue on GitHub
- Contact: contact@mlox.org
