/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      fontFamily: {
        // Clean, minimalistic, elegant sans-serif font
        // Change this to customize the site's font
        sans: ['Roboto', 'Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        // Monospace font for code blocks
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'Monaco', 'Courier New', 'monospace'],
      },
      colors: {
        // Brutalist warm-paper color scheme
        dark: {
          900: '#f6f1e6', // Primary surface
          800: '#efe6d2', // Alternate section surface
          700: '#e6dac0', // Card background
          600: '#d8c9a8', // Stronger contrast surface
        },
        // Muted high-contrast accents
        accent: {
          cyan: '#0f8b8d',    // Teal
          purple: '#4f5d75',  // Slate indigo
          pink: '#d16a4b',    // Burnt orange
          yellow: '#d3a321',  // Mustard
          green: '#5e7f3b',   // Olive green
        },
      },
      animation: {
        'fade-in': 'fadeIn 0.6s ease-in-out',
        'slide-up': 'slideUp 0.6s ease-out',
        'slide-down': 'slideDown 0.6s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(30px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-30px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
