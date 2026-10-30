/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      fontFamily: {
        // Aligns with the Google Fonts import in BaseLayout.astro
        display: ['"Bricolage Grotesque"', 'ui-sans-serif', 'sans-serif'],
        sans: ['"Bricolage Grotesque"', 'ui-sans-serif', 'sans-serif'],
        serif: ['"Instrument Serif"', 'ui-serif', 'Georgia', 'serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        // "Night canopy": the MLOX TUI palette, softened for reading
        canopy: {
          950: '#07110c',
          900: '#0b1912',
          800: '#10241a',
          700: '#173323',
          600: '#21452f',
        },
        cream: '#f3e9d2',
        moss: '#a9b8a3',
        lime: '#c5f06a',
        amber: '#f2b541',
        rose: '#ef7bb8',
        tree: '#7fd6d0',
      },
    },
  },
  plugins: [],
};
