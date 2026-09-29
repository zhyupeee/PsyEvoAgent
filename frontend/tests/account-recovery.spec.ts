import { expect, test } from '@playwright/test'

test('refresh keeps the navigation stable while identity is pending', async ({
  page,
}) => {
  let releaseIdentity = () => {}
  let identityReady = Promise.resolve()
  const requests: string[] = []
  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    requests.push(pathname)
    if (pathname.endsWith('/auth/session')) {
      await identityReady
      return route.fulfill({
        json: {
          user_id: 'synthetic-refresh',
          email: 'refresh@example.com',
          csrf_token: 'synthetic',
        },
      })
    }
    if (pathname.endsWith('/me/preferences'))
      return route.fulfill({
        json: {
          version: 1,
          age_band: 'unknown',
          mode: 'listen',
          display_preferences: {
            font_size: 'normal',
            reduced_motion: true,
            hide_titles: false,
          },
        },
      })
    return route.fulfill({ status: 503, json: { code: 'synthetic' } })
  })
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 900 })
    for (const refresh of [false, true]) {
      requests.length = 0
      identityReady = new Promise<void>((resolve) => {
        releaseIdentity = resolve
      })
      if (refresh) await page.reload()
      else await page.goto('/me?section=security')
      const main = page.locator('#support-main')
      await expect(main).toHaveAttribute('aria-busy', 'true')
      await expect(page.getByRole('status')).toHaveClass('sr-only')
      await expect(page.getByLabel('当前密码', { exact: true })).toHaveCount(0)
      expect(new Set(requests)).toEqual(new Set(['/api/v1/auth/session']))
      const settings = page.getByRole('link', { name: '设置', exact: true })
      const bounds = await settings.boundingBox()
      releaseIdentity()
      await expect(main).toHaveAttribute('aria-busy', 'false')
      await expect(page.getByLabel('当前密码', { exact: true })).toBeVisible()
      expect(await settings.boundingBox()).toEqual(bounds)
      await expect(page.getByRole('status')).toHaveCount(0)
    }
  }
})

test('session service failure stays on chat and retry restores login', async ({
  page,
}) => {
  let unavailable = true
  await page.route('**/api/v1/auth/session', (route) =>
    route.fulfill({
      status: unavailable ? 503 : 401,
      contentType: 'application/json',
      body: JSON.stringify({
        code: unavailable
          ? 'database_not_configured'
          : 'authentication_required',
      }),
    }),
  )
  await page.goto('/')
  await expect(page.getByRole('alert')).toHaveText(
    '无法确认登录状态，内容已隐藏。',
  )
  await expect(page).toHaveURL('/chat')
  await expect(page.getByText('欢迎回来。')).toHaveCount(0)
  unavailable = false
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page).toHaveURL('/login')
  await expect(
    page.getByRole('button', { name: '登录', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
