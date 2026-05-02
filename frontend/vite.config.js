import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/webhook': 'http://localhost:8000',
      '/stream': 'http://localhost:8000',
      '/deploy-stream': 'http://localhost:8000',
      '/approve': 'http://localhost:8000',
      '/incidents': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/audit': 'http://localhost:8000',
      '/runbook': 'http://localhost:8000',
      '/system-health': 'http://localhost:8000',
      '/memory-stats': 'http://localhost:8000',
      '/incident-queue': 'http://localhost:8000',
      '/orchestrate': 'http://localhost:8000'
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        quietDeps: true
      }
    }
  }
})
