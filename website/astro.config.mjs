import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

// https://astro.build/config
export default defineConfig({
  site: 'https://busysloths.github.io',
  base: '/mlox',
  build: {
    assets: 'assets'
  },
  integrations: [tailwind()]
});
