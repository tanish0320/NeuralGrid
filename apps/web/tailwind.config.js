/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        noc: {
          bg: '#0B0F19',
          surface: '#111827',
          card: '#182234',
          border: '#2A364E',
          divider: '#1F293D',
          hover: '#222E44',
          cyan: '#06B6D4',
          teal: '#0D9488',
          green: '#10B981',
          amber: '#F59E0B',
          red: '#EF4444',
        }
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
