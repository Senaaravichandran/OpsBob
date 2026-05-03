import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_BACKEND_TARGET || 'http://localhost:8001'
const apiProxyPaths = [
  '/webhook',
  '/stream',
  '/deploy-stream',
  '/approve',
  '/incidents',
  '/health',
  '/audit',
  '/runbook',
  '/system-health',
  '/memory-stats',
  '/incident-queue',
  '/orchestrate'
]
const proxy = Object.fromEntries(apiProxyPaths.map((path) => [path, backendTarget]))

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy
  },
  css: {
    preprocessorOptions: {
      scss: {
        quietDeps: true
      }
    }
  }
})
