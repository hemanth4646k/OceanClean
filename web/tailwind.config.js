/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        abyssal: {
          bg: '#040914',
          surface: '#0b1329',
          border: 'rgba(0, 240, 255, 0.2)',
        },
        cyan: {
          glow: '#00F0FF',
        },
        amber: {
          radar: '#F59E0B',
        },
        crimson: {
          coral: '#EF4444',
        },
        emerald: {
          harvest: '#10B981',
        },
        violet: {
          storm: '#A855F7',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        sans: ['Plus Jakarta Sans', 'Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

