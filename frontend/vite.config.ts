import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API is reached through /api so the browser never makes a cross-origin request in dev.
// API_URL lets a machine where port 8000 is taken (reset-demo.ps1 uses 8010) point somewhere else.
const API = process.env.API_URL ?? 'http://127.0.0.1:8000'
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: API, rewrite: (p) => p.replace(/^\/api/, '') } },
  },
  preview: {
    // A tunnel serves this under its own hostname, which the preview server would otherwise refuse
    allowedHosts: true,
    proxy: { '/api': { target: API, rewrite: (p) => p.replace(/^\/api/, '') } },
  },
})
