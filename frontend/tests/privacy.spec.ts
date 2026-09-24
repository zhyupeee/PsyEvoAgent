import { expect, test } from '@playwright/test'
import { mailCode, register } from './email-helper'

test.beforeEach(async ({ context }) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
})

test('code resend follows the edited email while an earlier send completes', async ({
  page,
}) => {
  const first = `first-${Date.now()}@example.com`
  const corrected = `corrected-${Date.now()}@example.com`
  let releaseFirst: () => void = () => undefined
  let firstStarted: () => void = () => undefined
  const firstPending = new Promise<void>((resolve) => {
    releaseFirst = resolve
  })
  const firstRequest = new Promise<void>((resolve) => {
    firstStarted = resolve
  })
  await page.route('**/api/v1/auth/registration-codes', async (route) => {
    if (route.request().postDataJSON().email === first) {
      firstStarted()
      await firstPending
    }
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'accepted' }),
    })
  })
  await page.goto('/register')
  const email = page.getByLabel('邮箱', { exact: true })
  const resend = page.getByRole('button', { name: '发送验证码' })
  await email.fill(first)
  await resend.click()
  await firstRequest
  try {
    await email.fill(corrected)
    await expect(resend).toBeEnabled()
    await resend.click()
    await expect(page.getByRole('status')).toContainText(corrected)
    const firstResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/v1/auth/registration-codes') &&
        response.request().postDataJSON().email === first,
    )
    releaseFirst()
    await firstResponse
    await expect(page.getByRole('status')).toContainText(corrected)
    await email.fill(first)
    await expect(page.getByRole('status')).toContainText(first)
    await expect(page.getByRole('button', { name: /秒后重发/ })).toBeDisabled()
  } finally {
    releaseFirst()
  }
})

test('email register, refresh, account change revokes sessions and logout', async ({
  page,
  context,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const email = `browser-${Date.now()}@example.com`
  await register(page, email)
  await expect(page.getByText(`当前账号：${email}`)).toBeVisible()
  await expect(page.locator('body')).not.toContainText(
    /年龄|同意|撤回|用途确认/,
  )
  await expect(page.locator('a[href="/chat"]')).toHaveCount(0)
  const cookie = (await context.cookies()).find(
    (item) => item.name === 'psyevo_session',
  )
  expect(
    cookie?.secure && cookie.httpOnly && cookie.sameSite === 'Strict',
  ).toBe(true)
  await page.reload()
  await expect(page.getByText(`当前账号：${email}`)).toBeVisible()
  await page.goto('/me/privacy')
  await expect(page).toHaveURL('/me')
  await page.getByLabel('当前密码').fill('incorrect')
  await page.getByLabel('新密码', { exact: true }).fill('changed-password')
  await page.getByLabel('确认新密码').fill('changed-password')
  await page.getByRole('button', { name: '修改密码并退出' }).click()
  await expect(page.getByRole('alert')).toHaveText('当前密码不正确。')
  await page.getByLabel('当前密码').fill('12345678')
  await page.getByRole('button', { name: '修改密码并退出' }).click()
  await expect(page).toHaveURL('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page.getByLabel('密码', { exact: true }).fill('12345678')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('邮箱或密码不正确。')
  await page.getByLabel('密码', { exact: true }).fill('changed-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/')
  await page.goto('/me')
  await expect(page.getByRole('heading', { name: '我的账号' })).toBeVisible()
  await page.screenshot({
    path: '../.artifacts/step035-account-desktop.png',
    fullPage: true,
  })
  await page.getByRole('button', { name: '退出账号' }).click()
  await expect(page).toHaveURL('/login')
  expect(errors).toEqual([])
})

test('forgot password and mobile keyboard recovery', async ({
  page,
  request,
}) => {
  expect(await (await request.get('/me')).text()).not.toContain('csrf_token')
  await page.setViewportSize({ width: 375, height: 812 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const email = `browser-reset-${Date.now()}@example.com`
  // Use the preexisting synthetic account to avoid registration resend cooldown.
  await page.goto('/login')
  await page.getByRole('button', { name: '忘记密码？' }).click()
  await page.getByLabel('邮箱', { exact: true }).fill('browser-b@example.com')
  await page.getByRole('button', { name: '发送验证码' }).click()
  await expect(page.getByRole('status')).toContainText('验证码已发送')
  await page
    .getByLabel('邮箱验证码', { exact: true })
    .fill(await mailCode('browser-b@example.com'))
  await page
    .getByLabel('新密码', { exact: true })
    .fill('reset-browser-password')
  await page.getByLabel('确认新密码').fill('reset-browser-password')
  await page.getByRole('button', { name: '重置密码', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('密码重置请求已完成')
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill('browser-b@example.com')
  await page.getByLabel('密码', { exact: true }).fill('reset-browser-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/')
  await page.context().clearCookies()
  await page.goto('/register')
  await page.getByLabel('邮箱', { exact: true }).focus()
  await page.keyboard.type(email)
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('邮箱验证码', { exact: true })).toBeFocused()
  await page.getByRole('button', { name: '发送验证码' }).click()
  await expect(page.getByRole('status')).toContainText('验证码已发送')
  await page
    .getByLabel('邮箱验证码', { exact: true })
    .fill(await mailCode(email))
  await page.getByLabel('密码', { exact: true }).fill('12345678')
  await page.getByLabel('确认新密码').fill('different-password')
  await page.getByRole('button', { name: '注册并进入' }).click()
  await expect(page.getByRole('alert')).toHaveText('两次输入的新密码不一致。')
  await page.getByLabel('确认新密码').fill('12345678')
  await page.route('**/api/v1/auth/register', (route) =>
    route.fulfill({ status: 503, body: 'private-response' }),
  )
  await page.getByRole('button', { name: '注册并进入' }).click()
  await expect(page.getByRole('alert')).toBeFocused()
  await expect(page.locator('body')).not.toContainText('private-response')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.screenshot({
    path: '../.artifacts/step035-register-mobile.png',
    fullPage: true,
  })
  await page.unroute('**/api/v1/auth/register')
  await page.getByRole('button', { name: '注册并进入' }).click()
  await expect(page).toHaveURL('/')
  await page.context().clearCookies()
  await page.reload()
  await expect(page).toHaveURL('/login')
})

test('brand and browser icon resources on all entry pages', async ({
  page,
  request,
}) => {
  for (const resource of [
    '/favicon.ico',
    '/brand/logo.png',
    '/brand/icon-16.png',
    '/brand/icon-32.png',
    '/brand/icon-48.png',
    '/brand/icon-180.png',
    '/brand/icon-192.png',
    '/brand/icon-512.png',
    '/site.webmanifest',
  ]) {
    const response = await request.get(resource)
    expect(response.status()).toBe(200)
    expect((await response.body()).length).toBeGreaterThan(100)
  }
  for (const route of ['/register', '/login', '/health']) {
    await page.goto(route)
    await expect(
      page.getByRole('link', { name: 'PsyEvoAgent 首页' }),
    ).toBeVisible()
    expect(
      await page
        .locator('img[src="/brand/logo.png"]')
        .evaluate(
          (node: HTMLImageElement) => node.complete && node.naturalWidth > 0,
        ),
    ).toBe(true)
    await expect(
      page.locator('link[rel="icon"][href="/favicon.ico"]'),
    ).toHaveCount(1)
    await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute(
      'href',
      '/brand/icon-180.png',
    )
    if (route !== '/health') await expect(page).not.toHaveTitle(/工程/)
  }
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill('admin@example.com')
  await page
    .getByLabel('密码', { exact: true })
    .fill('synthetic-admin-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/')
  for (const route of ['/', '/me']) {
    await page.goto(route)
    await expect(
      page.getByRole('link', { name: 'PsyEvoAgent 首页' }),
    ).toBeVisible()
  }
})
