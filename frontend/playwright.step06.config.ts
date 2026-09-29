import { defineConfig } from '@playwright/test'
import base from './playwright.step05.config'
export default defineConfig({
  ...base,
  testMatch: [
    'support.spec.ts',
    'chat-regressions.spec.ts',
    'feedback-ui.spec.ts',
  ],
})
