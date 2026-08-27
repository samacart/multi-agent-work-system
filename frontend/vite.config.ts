import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Docker bind mounts on macOS/Windows do not always deliver fs events.
    watch: { usePolling: true },
  },
})
