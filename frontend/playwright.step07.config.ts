import { defineConfig } from '@playwright/test'
import base from './playwright.step05.config'
export default defineConfig({ ...base, testMatch: ['history.spec.ts'] })
