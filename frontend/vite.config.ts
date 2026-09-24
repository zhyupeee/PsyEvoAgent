import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const localPortFallback =
  !process.env.PSYEVO_BROWSER_ORIGIN &&
  !process.env.PSYEVO_TEST_WEB_PORT &&
  (process.env.PSYEVO_ENV ?? 'development') === 'development'

export default defineConfig({
  envDir: false,
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: !localPortFallback,
    allowedHosts: process.env.PSYEVO_BROWSER_ORIGIN
      ? [new URL(process.env.PSYEVO_BROWSER_ORIGIN).hostname]
      : [],
    proxy: {
      '/api/v1': {
        target: `http://127.0.0.1:${process.env.PSYEVO_TEST_API_PORT ?? '8000'}`,
        configure(proxy) {
          if (!localPortFallback) return
          proxy.on('proxyReq', (proxyReq, request) => {
            const port = request.socket.localPort
            if (
              port &&
              port !== 3000 &&
              request.headers.origin === `http://127.0.0.1:${port}`
            ) {
              proxyReq.setHeader('origin', 'http://127.0.0.1:3000')
            }
          })
        },
      },
    },
  },
  plugins: [
    {
      name: 'replace-previous-development-server',
      apply: 'serve',
      configureServer(server) {
        if (
          process.env.VITEST ||
          process.env.PSYEVO_TEST_WEB_PORT ||
          (process.env.PSYEVO_ENV ?? 'development') !== 'development'
        ) {
          return
        }
        execFileSync(
          'uv',
          [
            'run',
            '--directory',
            fileURLToPath(new URL('../backend', import.meta.url)),
            '--no-sync',
            'python',
            '-m',
            'app.dev_instances',
            '--frontend-port',
            String(server.config.server.port ?? 3000),
            ...(localPortFallback ? ['--allow-port-fallback'] : []),
          ],
          { stdio: 'inherit' },
        )
      },
    },
    tailwindcss(),
    tanstackStart(),
    react(),
  ],
})
