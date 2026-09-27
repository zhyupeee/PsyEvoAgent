import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

async function login(
  page: Page,
  email = 'step05-unused@example.com',
  password = 'synthetic-browser-password',
) {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText(`当前账号：${email}`)).toBeVisible()
}
async function screenshot(page: Page, name: string) {
  const directory = process.env.PSYEVO_STEP06_ARTIFACTS
  if (!directory) throw new Error('Missing evidence directory')
  await page.screenshot({
    path: path.join(directory, name + '.png'),
    fullPage: true,
  })
}
test.beforeEach(async ({ context }) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
})

test('chat: real send, lost acknowledgement retry, snapshot reload, account isolation', async ({
  page,
  context,
}) => {
  await login(page)
  await page.getByRole('link', { name: '进入对话' }).click()
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await page.getByLabel('想说的事').fill('合成页面输入，只想倾听')
  let lost = false
  const keys: string[] = []
  await page.route('**/api/v1/runs/*/start', async (route) => {
    keys.push(route.request().headers()['idempotency-key'])
    if (!lost) {
      lost = true
      await route.fetch()
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('发送未确认')
  await expect(page.getByLabel('想说的事')).toHaveValue(
    '合成页面输入，只想倾听',
  )
  await page.getByRole('button', { name: '重试原消息' }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBe(keys[1])
  await expect(page.locator('.assistant-message')).not.toBeEmpty()
  const text = await page.locator('.assistant-message').innerText()
  const url = page.url()
  await page.reload()
  await expect(page.locator('.assistant-message')).toHaveText(text)
  await screenshot(page, 'chat-desktop')
  const other = await context
    .browser()!
    .newContext({ baseURL: new URL(url).origin })
  await other.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
  const otherPage = await other.newPage()
  await otherPage.goto(url)
  await expect(otherPage).toHaveURL(/\/login$/)
  await login(otherPage, 'step05-browser@example.com')
  await otherPage.goto(url)
  await expect(
    otherPage.getByRole('heading', { name: '对话暂不可用' }),
  ).toBeVisible()
  await expect(otherPage.locator('body')).not.toContainText(
    '合成页面输入，只想倾听',
  )
  await other.close()
})

test('confirmed lost start clears pending send and preserves a revised next message', async ({
  page,
}) => {
  await login(page, 'admin@example.com', 'synthetic-admin-password')
  await page.goto('/chat')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await page.getByLabel('想说的事').fill('合成状态查询前的输入')
  let starts = 0
  await page.route('**/api/v1/runs/*/start', async (route) => {
    starts++
    if (starts === 1) {
      await route.fetch()
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('发送未确认')
  await page.getByLabel('想说的事').fill('合成状态查询后的新输入')
  await page.getByRole('button', { name: '查询运行状态' }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByLabel('想说的事')).toHaveValue(
    '合成状态查询后的新输入',
  )
  expect(starts).toBe(1)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.locator('.user-message')).toHaveText(
    '合成状态查询后的新输入',
  )
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  expect(starts).toBe(2)
})

test('stop reflects backend terminal even when completion wins; stream loss recovers without send', async ({
  page,
}) => {
  await login(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  let starts = 0
  await page.route('**/api/v1/runs/*/start', async (route) => {
    starts++
    await route.continue()
  })
  await page.route('**/api/v1/runs/*/events*', (route) => route.abort('failed'))
  await page.getByLabel('想说的事').fill('合成取消检查')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const stop = page.getByRole('button', { name: '停止生成' })
  await stop.click()
  await expect(page.getByRole('status')).toContainText(/已停止|已完成/, {
    timeout: 20000,
  })
  expect(starts).toBe(1)
  const sid = page.url().split('/').at(-1)
  const run = await page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/sessions/${id}/current-run`)
    if (!response.ok) throw new Error(`snapshot ${response.status}`)
    return response.json() as Promise<{ status: string }>
  }, sid)
  expect(['completed', 'cancelled']).toContain(run.status)
  await expect(page.getByRole('status')).toContainText(
    run.status === 'completed' ? '已完成' : '已停止',
  )
})

test('preferences: failure is not saved; persistence, mobile keyboard and title display', async ({
  page,
}) => {
  await login(page)
  await page.goto('/me')
  await page
    .getByRole('combobox', { name: '字号', exact: true })
    .selectOption('large')
  await page.getByLabel('隐藏对话标题').check()
  await page.route('**/api/v1/me/preferences', (route) =>
    route.request().method() === 'PATCH'
      ? route.fulfill({ status: 503, json: { code: 'storage_unavailable' } })
      : route.continue(),
  )
  await page.getByRole('button', { name: '保存偏好' }).click()
  await expect(page.getByRole('alert')).toContainText('未保存')
  await page.unroute('**/api/v1/me/preferences')
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith('/me/preferences') &&
      response.request().method() === 'PATCH' &&
      response.ok(),
  )
  await page.getByRole('button', { name: '保存偏好' }).click()
  await saved
  await page.reload()
  await expect(
    page.getByRole('combobox', { name: '字号', exact: true }),
  ).toHaveValue('large')
  await expect(page.getByLabel('隐藏对话标题')).toBeChecked()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/chat')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await expect(page.locator('.chat-title')).toHaveText('对话')
  await expect(page.locator('.support-shell')).toHaveAttribute(
    'data-large',
    'true',
  )
  await page.getByLabel('想说的事').focus()
  await page.keyboard.type('synthetic keyboard')
  await page.keyboard.press('Tab')
  await expect(
    page.getByRole('button', { name: '发送', exact: true }),
  ).toBeFocused()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await screenshot(page, 'chat-mobile')
})

test('independent exercise: no model requests, skip, exit, refresh, unknown resources', async ({
  page,
}) => {
  await login(page)
  const modelRequests: string[] = []
  page.on('request', (request) => {
    if (/\/run-drafts|\/runs\/|\/interaction-events/.test(request.url()))
      modelRequests.push(request.url())
  })
  await page.route('**/api/v1/runs/**', (route) =>
    route.fulfill({ status: 503, json: { code: 'provider_not_configured' } }),
  )
  await page.goto('/resources')
  await page.getByRole('link', { name: '查看练习' }).click()
  await expect(page.getByText(/synthetic-attention\/1/)).toBeVisible()
  await page.getByRole('button', { name: '开始练习' }).click()
  await page.getByRole('button', { name: '跳过', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('第 2 / 3 步')
  await screenshot(page, 'exercise-desktop')
  await page.getByRole('link', { name: '退出练习，返回资源' }).click()
  await page.getByRole('link', { name: '查看练习' }).click()
  await expect(page.getByRole('button', { name: '开始练习' })).toBeVisible()
  await page.getByRole('button', { name: '开始练习' }).click()
  await page.reload()
  await expect(page.getByRole('button', { name: '开始练习' })).toBeVisible()
  await page.getByRole('button', { name: '开始练习' }).click()
  for (let i = 0; i < 3; i++)
    await page.getByRole('button', { name: '下一步' }).click()
  await expect(
    page.getByRole('heading', { name: '练习到这里结束' }),
  ).toBeFocused()
  await page.getByRole('link', { name: '返回资源', exact: true }).click()
  await page.getByRole('link', { name: '现实支持', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: '暂无已核实的校内值班信息' }),
  ).toBeVisible()
  expect(modelRequests).toEqual([])
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([])
  await page.setViewportSize({ width: 390, height: 844 })
  await screenshot(page, 'resources-mobile')
})
