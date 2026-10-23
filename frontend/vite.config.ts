import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API is reached through /api so the browser never makes a cross-origin request in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: 'http://127.0.0.1:8000', rewrite: (p) => p.replace(/^\/api/, '') } },
  },
  preview: {
    // A tunnel serves this under its own hostname, which the preview server would otherwise refuse
    allowedHosts: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', rewrite: (p) => p.replace(/^\/api/, '') } },
  },
})
