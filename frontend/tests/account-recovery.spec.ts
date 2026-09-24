import { expect, test } from '@playwright/test'

test('session service failure stays on home and retry restores login', async ({
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
    '服务暂时不可用，请稍后重试。',
  )
  await expect(page).toHaveURL('/')
  await expect(page.getByText('欢迎回来。')).toHaveCount(0)
  unavailable = false
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(page).toHaveURL('/login')
  await expect(
    page.getByRole('button', { name: '登录', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
