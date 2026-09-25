import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev proxy: API běží na jiném portu než vite dev server.
    // Cíl se dá přepsat env proměnnou (např. VITE_DEV_PROXY_TARGET=http://127.0.0.1:8123).
    proxy: {
      '/api/v1': {
        target: process.env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})