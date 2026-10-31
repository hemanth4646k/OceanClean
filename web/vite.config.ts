import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies like nginx in the web container: /api -> API (prefix stripped), /ws -> API.
// The API's host port from infra/docker-compose.yml.
const API = 'http://localhost:8002'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // One ~550 kB bundle (React, Leaflet, land polygons) served locally; no need to split it.
  build: { chunkSizeWarningLimit: 1000 },
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    proxy: {
      '/api': { target: API, rewrite: (p) => p.replace(/^\/api/, '') },
      '/ws': { target: API.replace(/^http/, 'ws'), ws: true },
    },
  },
})
