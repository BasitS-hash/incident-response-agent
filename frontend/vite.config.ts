import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/incident': 'http://127.0.0.1:8000',
      '/approve': 'http://127.0.0.1:8000',
      '/stream': 'http://127.0.0.1:8000',
      '/incidents': 'http://127.0.0.1:8000',
      '/runs': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    }
  }
})
