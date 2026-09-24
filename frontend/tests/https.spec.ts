import { expect, test } from '@playwright/test'
import { register } from './email-helper'

test('configured HTTPS origin, secure cookie, icons and rejected alternate origin', async ({
  page,
  context,
}) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
  await register(page, `browser-https-${Date.now()}@example.com`)
  await expect(page.getByRole('heading', { name: '欢迎回来。' })).toBeVisible()
  expect(page.url()).toMatch(/^https:/)
  expect(
    (await context.cookies()).find((c) => c.name === 'psyevo_session')?.secure,
  ).toBe(true)
  await page.reload()
  await expect(page.getByRole('heading', { name: '欢迎回来。' })).toBeVisible()
  expect((await context.request.get('/favicon.ico')).status()).toBe(200)
  expect((await context.request.get('/brand/icon-180.png')).status()).toBe(200)
  const result = await context.request.post('/api/v1/auth/registration-codes', {
    headers: { Origin: 'https://not-configured.example' },
    data: { email: 'must-not-exist@example.com' },
  })
  expect(result.status()).toBe(403)
  await page.goto('/me')
  await page.getByRole('button', { name: '退出账号' }).click()
  await expect(page).toHaveURL('/login')
})
