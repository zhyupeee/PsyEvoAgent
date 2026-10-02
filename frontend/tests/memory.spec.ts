import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

async function login(page: Page) {
  await page.goto('/login')
  await page
    .getByLabel('邮箱', { exact: true })
    .fill('s2-memory-browser@example.com')
  await page
    .getByLabel('密码', { exact: true })
    .fill('synthetic-browser-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/chat')
}

async function addMemory(page: Page) {
  const text = '合成记忆 ' + Date.now() + '：我喜欢散步。'
  await page.goto('/records')
  await page.getByRole('button', { name: '新建笔记' }).click()
  await page.getByLabel('正文', { exact: true }).fill(text)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText(text, { exact: true })).toBeVisible()
  await page.goto('/me/memories')
  await expect(page.getByRole('heading', { name: text })).toBeVisible({
    timeout: 20000,
  })
  return {
    text,
    card: page
      .locator('.memory-card')
      .filter({ has: page.getByRole('heading', { name: text }) }),
  }
}

test.beforeEach(async ({ context }) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
})

test('S2-A04 real page auto-save, correction, reopen and confirmed forgetting', async ({
  page,
}) => {
  await login(page)
  const { text, card } = await addMemory(page)
  await expect(card).toContainText('你的记录')
  await expect(card).toContainText('未知')
  const directory = process.env.PSYEVO_S2_STEP04_ARTIFACTS
  if (!directory) throw new Error('Missing evidence directory')
  await page.screenshot({
    path: path.join(directory, 'memory-desktop.png'),
    fullPage: true,
  })
  await card.getByRole('button', { name: '更正', exact: true }).click()
  await page.getByLabel('更正内容').fill('更正后的合成记忆：只是今天想散步。')
  await page.getByRole('button', { name: '保存更正' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page.reload()
  const corrected = page
    .locator('.memory-card')
    .filter({ hasText: '更正后的合成记忆：只是今天想散步。' })
  await expect(corrected).toBeVisible()
  await corrected.getByRole('button', { name: '遗忘', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('保留原始记录')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(corrected).toBeVisible()
  await corrected.getByRole('button', { name: '遗忘', exact: true }).click()
  await page.getByRole('button', { name: '确认遗忘' }).click()
  await expect(corrected).not.toBeVisible()
  await page.reload()
  await expect(
    page.getByText('更正后的合成记忆：只是今天想散步。'),
  ).not.toBeVisible()
  await page.goto('/records')
  await expect(
    page
      .getByRole('button', { name: '未命名笔记 已保存', exact: true })
      .first(),
  ).toBeVisible()
  await page
    .getByRole('button', { name: '未命名笔记 已保存', exact: true })
    .first()
    .click()
  await expect(page.getByText(text, { exact: true })).toBeVisible()
})

test('mobile stop filter, errors and no horizontal overflow', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page)
  const { text, card } = await addMemory(page)
  await card.getByRole('button', { name: '停止使用' }).click()
  await page.getByRole('button', { name: '确认停止' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await page.getByRole('combobox', { name: '记忆状态' }).click()
  await page.getByRole('option', { name: '已停止', exact: true }).click()
  await expect(page.getByRole('heading', { name: text })).toBeVisible()
  const directory = process.env.PSYEVO_S2_STEP04_ARTIFACTS
  if (!directory) throw new Error('Missing evidence directory')
  await page.screenshot({
    path: path.join(directory, 'memory-mobile.png'),
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.route('**/api/v1/memories?**', (route) =>
    route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }),
  )
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('暂时无法读取')
  await page.unroute('**/api/v1/memories?**')
  await page.getByRole('button', { name: '刷新', exact: true }).click()
  await expect(page.getByRole('alert')).not.toBeVisible()
})

test('failed save preserves edit, conflict requires review and escape retains dirty form', async ({
  page,
}) => {
  await login(page)
  const { card } = await addMemory(page)
  const edited = '我的编辑需要保留 ' + Date.now()
  await card.getByRole('button', { name: '更正', exact: true }).click()
  await page.getByLabel('更正内容').fill(edited)
  let failed = false
  await page.route('**/api/v1/memories/*', async (route) => {
    if (route.request().method() === 'PATCH' && !failed) {
      failed = true
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: '{}',
      })
    } else await route.continue()
  })
  await page.getByRole('button', { name: '保存更正' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByLabel('更正内容')).toHaveValue(edited)
  await page.getByRole('button', { name: '保存更正' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  const current = page.locator('.memory-card').filter({ hasText: edited })
  await current.getByRole('button', { name: '更正', exact: true }).click()
  await page.getByLabel('更正内容').fill('尚未保存的编辑')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog').last()).toContainText('放弃未保存')
  await page.getByRole('button', { name: '继续编辑' }).click()
  await expect(page.getByLabel('更正内容')).toHaveValue('尚未保存的编辑')
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(
    '尚未保存的编辑',
  )
})

test('concurrent correction shows latest content and preserves the editor', async ({
  page,
}) => {
  await login(page)
  const { text, card } = await addMemory(page)
  const edited = '本窗口的更正 ' + Date.now()
  await card.getByRole('button', { name: '更正', exact: true }).click()
  await page.getByLabel('更正内容').fill(edited)
  await page.evaluate(async (content) => {
    const auth = await (await fetch('/api/v1/auth/session')).json()
    const list = await (await fetch('/api/v1/memories')).json()
    const item = list.items.find(
      (row: { content: string }) => row.content === content,
    )
    const response = await fetch('/api/v1/memories/' + item.id, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': auth.csrf_token,
        'Idempotency-Key': crypto.randomUUID(),
      },
      body: JSON.stringify({
        expected_version: item.version,
        content: '另一窗口已经更正',
      }),
    })
    if (!response.ok) throw new Error('Concurrent synthetic update failed')
  }, text)
  await page.getByRole('button', { name: '保存更正' }).click()
  await expect(page.getByRole('alert')).toContainText('版本冲突')
  await expect(page.getByLabel('更正内容')).toHaveValue(edited)
  await expect(page.getByRole('dialog')).toContainText('另一窗口已经更正')
  await page.getByRole('button', { name: '已核对，保留我的修改' }).click()
  await page.getByRole('button', { name: '保存更正' }).click()
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.getByRole('heading', { name: edited })).toBeVisible()
})
