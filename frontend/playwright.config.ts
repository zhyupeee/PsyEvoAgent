import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: ['foundation.spec.ts', 'account-recovery.spec.ts'],
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:3000',
    browserName: 'chromium',
    serviceWorkers: 'block',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    launchOptions: {
      args: ['--disable-background-networking', '--disable-component-update'],
    },
  },
  webServer:
    process.env.PSYEVO_MANAGED_SERVERS === '1'
      ? []
      : [
          {
            command:
              'uv run --offline --no-sync uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log',
            cwd: '../backend',
            url: 'http://127.0.0.1:8000/api/v1/health',
            reuseExistingServer: false,
            env: { PSYEVO_ENV: 'test' },
          },
          {
            command: 'pnpm dev',
            env: { PSYEVO_ENV: 'test' },
            url: 'http://127.0.0.1:3000',
            reuseExistingServer: false,
            timeout: 60000,
          },
        ],
})
