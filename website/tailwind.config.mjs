/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    // Override defaults to enforce brutalist design system (no border-radius, flat shadows)
    borderRadius: {
      'none': '0',
      'sm': '0',
      DEFAULT: '0',
      'md': '0',
      'lg': '0',
      'xl': '0',
      '2xl': '0',
      '3xl': '0',
      'full': '0',
    },
    boxShadow: {
      'sm': '3px 3px 0 #1f1b16',
      DEFAULT: '6px 6px 0 #1f1b16',
      'md': '6px 6px 0 #1f1b16',
      'lg': '6px 6px 0 #1f1b16',
      'xl': '8px 8px 0 #1f1b16',
      '2xl': '10px 10px 0 #1f1b16',
      'inner': 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)',
      'none': 'none',
    },
    extend: {
      fontFamily: {
        // Aligns with Google Fonts import in BaseLayout.astro
        sans: ['Space Grotesk', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'Monaco', 'monospace'],
      },
      colors: {
        // Design tokens
        ink: '#1f1b16',
        paper: '#f6f1e6',
        'paper-alt': '#e9dec7',
        'paper-footer': '#e3d6bf',
        'paper-bright': '#fbf7ee',
        // Brutalist warm-paper surface tones
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
