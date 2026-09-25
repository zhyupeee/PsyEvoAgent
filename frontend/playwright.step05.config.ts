import { defineConfig } from '@playwright/test'
import base from './playwright.config'

if (
  !process.env.PSYEVO_DATABASE_URL ||
  process.env.PSYEVO_SUPPORT_MODE !== 'fake'
)
  throw new Error(
    'STEP05 requires an isolated synthetic database and fake worker',
  )

export default defineConfig({
  ...base,
  testMatch: ['runs.spec.ts'],
  use: {
    ...base.use,
    baseURL: `http://127.0.0.1:${process.env.PSYEVO_TEST_WEB_PORT ?? '3105'}`,
  },
  webServer: [
    {
      command: `uv run --offline --no-sync uvicorn tests.run_gateway:create_gateway_app --factory --host 127.0.0.1 --port ${process.env.PSYEVO_TEST_API_PORT ?? '8105'} --no-access-log`,
      cwd: '../backend',
      url: `http://127.0.0.1:${process.env.PSYEVO_TEST_API_PORT ?? '8105'}/api/v1/health`,
      reuseExistingServer: false,
    },
    {
      command: `pnpm dev --port ${process.env.PSYEVO_TEST_WEB_PORT ?? '3105'}`,
      url: `http://127.0.0.1:${process.env.PSYEVO_TEST_WEB_PORT ?? '3105'}`,
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
})
