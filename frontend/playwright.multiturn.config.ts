import { defineConfig } from '@playwright/test'
import base from './playwright.step08.config'

export default defineConfig({
  ...base,
  testMatch: ['multiturn-live.spec.ts'],
  timeout: 300000,
})
