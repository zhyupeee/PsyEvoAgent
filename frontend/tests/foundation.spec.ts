import { expect, test } from '@playwright/test'

test.beforeEach(async ({ context }) => {
  // Browser requests are independently restricted, including redirects.
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (url.hostname !== '127.0.0.1') return route.abort('blockedbyclient')
    await route.continue()
  })
})

test('real Start page and same-origin FastAPI gateway work twice with keyboard', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText(
    '先确认连接',
  )
  const check = page.getByRole('button', { name: '检查连接', exact: true })
  await expect(page.locator('body')).toHaveCSS(
    'background-color',
    'rgb(243, 241, 233)',
  )
  await expect(check).toHaveCSS('min-height', '48px')
  await expect(check).toBeEnabled()
  await page.keyboard.press('Tab')
  await expect(check).toBeFocused()
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.keyboard.press('Enter')
    await expect(page.getByRole('status')).toHaveText('API 已连接 · S1-STEP02')
  }
  expect(errors).toEqual([])
})

test('slow request can be stopped and late success cannot overwrite it', async ({
  page,
}) => {
  let release!: () => void
  let started!: () => void
  const waiting = new Promise<void>((resolve) => {
    release = resolve
  })
  const received = new Promise<void>((resolve) => {
    started = resolve
  })
  await page.route('**/api/v1/health', async (route) => {
    started()
    await waiting
    await route.fulfill({ json: { status: 'ok', stage: 'S1-STEP02' } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: '检查连接', exact: true }).click()
  await received
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '停止检查' })).toBeFocused()
  await page.keyboard.press('Enter')
  release()
  await expect(page.getByRole('status')).toHaveText('已停止检查')
  await expect(
    page.getByRole('button', { name: '检查连接', exact: true }),
  ).toBeFocused()
})

test('errors focus the message, never display raw bodies, and allow retry', async ({
  page,
}) => {
  await page.route('**/api/v1/health', (route) =>
    route.fulfill({ status: 503, body: 'synthetic-private-body' }),
  )
  await page.goto('/')
  await page.getByRole('button', { name: '检查连接', exact: true }).click()
  await expect(page.getByRole('alert')).toBeFocused()
  await expect(page.getByRole('alert')).toContainText('连接未完成')
  await expect(page.locator('body')).not.toContainText('synthetic-private-body')
  await page.unroute('**/api/v1/health')
  await page.getByRole('button', { name: '检查连接', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('API 已连接 · S1-STEP02')
})

test('mobile reduced-motion layout fits and external browser requests are denied', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await expect(
    page.getByRole('button', { name: '检查连接', exact: true }),
  ).toBeInViewport()
  expect(
    await page.evaluate(async () => {
      try {
        await fetch('https://model.invalid/probe')
        return 'allowed'
      } catch {
        return 'blocked'
      }
    }),
  ).toBe('blocked')
})
