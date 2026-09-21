import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  envDir: false,
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: true,
    proxy: { '/api/v1': { target: 'http://127.0.0.1:8000' } },
  },
  plugins: [tailwindcss(), tanstackStart(), react()],
})
