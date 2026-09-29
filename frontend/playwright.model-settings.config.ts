import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  testMatch: ['model-settings.spec.ts'],
  timeout: 60000,
  use: { ...base.use, baseURL: 'http://127.0.0.1:3110' },
  webServer: [],
})
