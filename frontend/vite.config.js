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
      '/health': 'http://localhost:8000'
    }
  }
})

// Made with Bob
