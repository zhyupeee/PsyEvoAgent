import { defineConfig } from '@playwright/test'
import base from './playwright.config'

if (!process.env.PSYEVO_STEP08_ARTIFACTS || process.env.PSYEVO_PROVIDER_API_KEY)
  throw new Error(
    'STEP08 requires its isolated launcher and a credential-free browser',
  )

export default defineConfig({
  ...base,
  testMatch: ['live.spec.ts'],
  timeout: 180000,
  use: {
    ...base.use,
    baseURL: `http://127.0.0.1:${process.env.PSYEVO_TEST_WEB_PORT}`,
  },
  webServer: {
    command: `pnpm dev --port ${process.env.PSYEVO_TEST_WEB_PORT}`,
    url: `http://127.0.0.1:${process.env.PSYEVO_TEST_WEB_PORT}`,
    reuseExistingServer: false,
    timeout: 60000,
  },
})
