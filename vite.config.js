import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Local dev only: forward API calls to `uvicorn index:app --port 8000` in api/
  // (API_PROXY=http://127.0.0.1:8001 npm run dev points it at another backend)
  server: {
    proxy: {
      '/api': process.env.API_PROXY || 'http://localhost:8000',
    },
    // The Python side (api/, its virtualenvs and caches) is not frontend code; watching its
    // thousands of files exhausts the system's file watcher limit and stops the dev server
    watch: {
      ignored: ['**/api/**', '**/.venv/**', '**/venv/**', '**/__pycache__/**', '**/examples/**'],
    },
  },
})
