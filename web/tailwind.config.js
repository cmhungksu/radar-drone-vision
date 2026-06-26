/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        radar: {
          green: '#16a34a',
          'green-dim': '#0d6b30',
          'green-glow': '#22c55e',
          dark: '#0b0f19',
          panel: '#111827',
          surface: '#1e293b',
          border: '#334155',
          muted: '#94a3b8',
          amber: '#f59e0b',
          red: '#ef4444',
          blue: '#3b82f6',
          cyan: '#06b6d4',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
    },
  },
  plugins: [],
};
