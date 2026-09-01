import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Binds every interface so a phone on the same Wi-Fi can reach it. The
    // app has no authentication, so on an untrusted network (university
    // Wi-Fi) this lets anyone there read your lectures. Set to false, or
    // run `npm run dev -- --host 127.0.0.1`, to keep it to this machine.
    host: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
