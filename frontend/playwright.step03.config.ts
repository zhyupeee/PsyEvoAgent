import { defineConfig } from '@playwright/test'
import base from './playwright.config'

if (!process.env.PSYEVO_DATABASE_URL)
  throw new Error(
    'STEP03 requires an explicit isolated synthetic PostgreSQL database',
  )

export default defineConfig({
  ...base,
  use: {
    ...base.use,
    baseURL: `http://127.0.0.1:${process.env.PSYEVO_TEST_WEB_PORT ?? '3000'}`,
  },
  testMatch: [
    'foundation.spec.ts',
    'privacy.spec.ts',
    'account-recovery.spec.ts',
  ],
  webServer: [
    {
      command: `uv run --offline --no-sync uvicorn tests.mail_support:create_test_app --factory --host 127.0.0.1 --port ${process.env.PSYEVO_TEST_API_PORT ?? '8000'} --no-access-log`,
      cwd: '../backend',
      url: `http://127.0.0.1:${process.env.PSYEVO_TEST_API_PORT ?? '8000'}/api/v1/health`,
      reuseExistingServer: false,
      env: {
        PSYEVO_ENV: 'test',
        PSYEVO_DATABASE_URL: process.env.PSYEVO_DATABASE_URL,
      },
    },
    {
      command: `pnpm dev --port ${process.env.PSYEVO_TEST_WEB_PORT ?? '3000'}`,
      env: { PSYEVO_ENV: 'test' },
      url: `http://127.0.0.1:${process.env.PSYEVO_TEST_WEB_PORT ?? '3000'}`,
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
})
