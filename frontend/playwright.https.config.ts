import { defineConfig } from '@playwright/test'
import base from './playwright.step03.config'

export default defineConfig({
  ...base,
  testMatch: 'https.spec.ts',
  use: {
    ...base.use,
    baseURL: process.env.PSYEVO_BROWSER_ORIGIN,
    ignoreHTTPSErrors: true,
  },
  webServer: [
    ...(Array.isArray(base.webServer) ? base.webServer : []),
    {
      command: 'node ../scripts/https-test-proxy.cjs',
      url: process.env.PSYEVO_BROWSER_ORIGIN,
      ignoreHTTPSErrors: true,
      reuseExistingServer: false,
    },
  ],
})
