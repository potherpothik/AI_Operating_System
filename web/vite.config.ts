import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Phase 24 doc §4: dev proxies /api/v1 -> Gateway, /ui -> control-ui BFF.
// Real service ports, matching every other service's own documented default
// (root README's status table / each service's own README "Run it" section).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api/v1': { target: 'http://localhost:8002', changeOrigin: true },
      '/ui': { target: 'http://localhost:8024', changeOrigin: true },
      '/metrics': { target: 'http://localhost:8013', changeOrigin: true },
      '/health': { target: 'http://localhost:8013', changeOrigin: true },
    },
  },
})
