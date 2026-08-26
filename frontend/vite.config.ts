import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // reachable from phone on the same Wi-Fi
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
