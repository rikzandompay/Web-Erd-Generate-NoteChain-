/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Theme tokens from DESIGN.md; the values live in index.css per theme
      colors: {
        desk: 'var(--desk)',
        panel: 'var(--panel)',
        ink: 'var(--ink)',
        muted: 'var(--muted)',
        line: 'var(--line)',
        edge: 'var(--edge)',
        accent: 'var(--accent)',
        'accent-hover': 'var(--accent-hover)',
        'on-accent': 'var(--on-accent)',
        danger: 'var(--danger)',
        'danger-bg': 'var(--danger-bg)',
        paper: 'var(--paper)',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
