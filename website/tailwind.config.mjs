/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        // Dark color scheme
        dark: {
          900: '#0a0e1a', // Darkest background
          800: '#121827', // Dark background
          700: '#1a2332', // Card background
          600: '#2a3446', // Lighter card
        },
        // Playful accent colors
        accent: {
          cyan: '#00e5ff',    // Bright cyan
          purple: '#a855f7',  // Vibrant purple
          pink: '#ec4899',    // Hot pink
          yellow: '#fbbf24',  // Warm yellow
          green: '#10b981',   // Bright green
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
