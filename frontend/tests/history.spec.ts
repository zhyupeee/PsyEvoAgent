import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

async function login(page: Page, email = 'step07-browser@example.com') {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page
    .getByLabel('密码', { exact: true })
    .fill('synthetic-browser-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByText('当前账号：' + email)).toBeVisible()
}
async function conversation(page: Page, text: string, email?: string) {
  await login(page, email)
  await page.goto('/chat')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await page.getByLabel('想说的事').fill(text)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
}
async function screenshot(page: Page, name: string) {
  const directory = process.env.PSYEVO_STEP07_ARTIFACTS
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

test('optional feedback: failure, empty reason, lost acknowledgement and real receipt', async ({
  page,
}) => {
  await conversation(page, 'STEP07反馈合成输入')
  await page.getByText('反馈或纠正 · 可跳过', { exact: true }).click()
  await page.getByLabel('这次回答').selectOption('unhelpful')
  await page.getByLabel('反馈类型').selectOption('misunderstood')
  let attempts = 0
  const keys: string[] = []
  let id = ''
  await page.route('**/api/v1/feedback', async (route) => {
    keys.push(route.request().headers()['idempotency-key'])
    const body = route.request().postDataJSON()
    expect(body.comment).toBe('')
    expect(Object.keys(body).sort()).toEqual([
      'category',
      'comment',
      'helpfulness',
      'run_id',
    ])
    attempts++
    if (attempts === 1)
      await route.fulfill({
        status: 503,
        json: { code: 'storage_unavailable' },
      })
    else if (attempts === 2) {
      id = (await (await route.fetch()).json()).feedback_id
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByRole('button', { name: '提交反馈' }).click()
  await expect(page.getByRole('alert')).toContainText('反馈未确认')
  await expect(page.getByText('反馈已保存', { exact: false })).toHaveCount(0)
  await page.getByRole('button', { name: '提交反馈' }).click()
  await expect.poll(() => id).not.toBe('')
  await expect(page.getByRole('button', { name: '提交反馈' })).toBeEnabled()
  await page.getByRole('button', { name: '提交反馈' }).click()
  await expect(page.getByText('反馈已保存，回执：' + id)).toBeVisible()
  expect(new Set(keys).size).toBe(1)
  await screenshot(page, 'feedback-desktop')
})

test('rename search archive restore, revision and regenerate preserve separate history', async ({
  page,
}) => {
  await conversation(page, 'STEP07旧输入不可混入')
  await page.getByText('管理此对话', { exact: true }).click()
  await page.getByLabel('对话标题').fill('STEP07检索对话')
  await page.getByRole('button', { name: '保存标题' }).click()
  await expect(
    page.getByRole('heading', { name: 'STEP07检索对话', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: '归档对话', exact: true }).click()
  await expect(page.getByText('此对话已归档，恢复后可继续发送。')).toBeVisible()
  await page.getByLabel('会话范围').selectOption('archived')
  await page.getByLabel('搜索标题').fill('STEP07检索')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await expect(
    page.getByRole('link', { name: 'STEP07检索对话', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: '恢复归档' }).click()
  await expect(
    page.getByRole('button', { name: '归档对话', exact: true }),
  ).toBeEnabled()
  await page.getByText('修订最后输入', { exact: true }).click()
  await page.getByLabel('修订内容').fill('   ')
  await page.getByRole('button', { name: '保存修订并生成' }).click()
  await expect(page.getByRole('alert')).toContainText('操作未确认')
  await page.getByLabel('修订内容').fill('STEP07修订后的独立输入')
  await page.getByRole('button', { name: '保存修订并生成' }).click()
  await expect(page.locator('.user-message')).toHaveText(
    'STEP07修订后的独立输入',
  )
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await page.getByRole('button', { name: '重新生成', exact: true }).click()
  await expect(
    page.getByRole('button', { name: '重新生成', exact: true }),
  ).toBeEnabled({ timeout: 20000 })
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await page.getByText('历史轮次与旧分支', { exact: true }).click()
  await expect(page.locator('.history-turn')).toHaveCount(2)
  await expect(
    page.locator('.history-turn').filter({ hasText: 'STEP07旧输入不可混入' }),
  ).toContainText('旧分支')
  await page.reload()
  await expect(page.locator('.user-message')).toHaveText(
    'STEP07修订后的独立输入',
  )
  await screenshot(page, 'history-desktop')
})

test('ordinary changes refresh the affected tab and preserve unrelated unsent forms', async ({
  page,
  context,
}) => {
  await conversation(
    page,
    'STEP07 cross-tab source',
    'step07-unused@example.com',
  )
  const same = await context.newPage()
  await same.goto(page.url())
  await same.getByLabel('想说的事').fill('same conversation unsent')
  const other = await context.newPage()
  await other.goto('/chat')
  await other.getByRole('button', { name: '开始一次对话' }).click()
  await other.getByLabel('想说的事').fill('unrelated original')
  await other.getByRole('button', { name: '发送', exact: true }).click()
  await expect(other.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await other.getByLabel('想说的事').fill('unsent composer')
  await other.getByText('修订最后输入', { exact: true }).click()
  await other.getByLabel('修订内容').fill('unsent revision')
  await other.getByText('反馈或纠正 · 可跳过', { exact: true }).click()
  await other.getByLabel('补充说明（可选）').fill('unsent feedback')
  let navigations = 0
  other.on('framenavigated', (frame) => {
    if (frame === other.mainFrame()) navigations++
  })
  await page.getByText('管理此对话', { exact: true }).click()
  await page.getByLabel('对话标题').fill('cross-tab renamed')
  await page.getByRole('button', { name: '保存标题' }).click()
  await expect(
    same.getByRole('heading', { name: 'cross-tab renamed', exact: true }),
  ).toBeVisible()
  await expect(same.getByLabel('想说的事')).toHaveValue(
    'same conversation unsent',
  )
  await page.getByRole('button', { name: '归档对话', exact: true }).click()
  await expect(same.getByText('此对话已归档，恢复后可继续发送。')).toBeVisible()
  await page.getByRole('button', { name: '恢复归档' }).click()
  await expect(same.getByText('此对话已归档，恢复后可继续发送。')).toHaveCount(
    0,
  )
  await page.getByText('修订最后输入', { exact: true }).click()
  await page.getByLabel('修订内容').fill('')
  await page.getByRole('button', { name: '保存修订并生成' }).click()
  await expect(page.getByRole('alert')).toContainText('操作未确认')
  const regenerated = page.waitForResponse(async (response) => {
    if (!response.url().endsWith('/current-run') || response.status() !== 200)
      return false
    const run = await response.json()
    return run?.input_version === 2 && run?.status === 'completed'
  })
  await page.getByRole('button', { name: '重新生成', exact: true }).click()
  await regenerated
  await expect(
    page.getByRole('button', { name: '重新生成', exact: true }),
  ).toBeEnabled({ timeout: 20000 })
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByText('修订最后输入', { exact: true }).click()
  await page.getByLabel('修订内容').fill('cross-tab revised')
  await page.getByRole('button', { name: '保存修订并生成' }).click()
  await expect(same.locator('.user-message')).toHaveText('cross-tab revised')
  await expect(other.getByLabel('想说的事')).toHaveValue('unsent composer')
  await expect(other.getByLabel('修订内容')).toHaveValue('unsent revision')
  await expect(other.getByLabel('补充说明（可选）')).toHaveValue(
    'unsent feedback',
  )
  expect(navigations).toBe(0)
  await same.close()
  await other.close()
})

test('confirmed deletion clears two tabs, retries lost response, survives logout and back', async ({
  page,
  context,
}) => {
  await conversation(page, 'STEP07删除后不再可见')
  const url = page.url()
  const other = await context.newPage()
  await other.goto(url)
  await expect(other.locator('.user-message')).toHaveText(
    'STEP07删除后不再可见',
  )
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByText('管理此对话', { exact: true }).click()
  await page.getByRole('button', { name: '删除会话', exact: true }).click()
  await expect(page.getByRole('button', { name: '暂不删除' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(page.locator('.user-message')).toHaveText('STEP07删除后不再可见')
  await page.getByRole('button', { name: '删除会话', exact: true }).click()
  await screenshot(page, 'delete-mobile')
  let lost = false
  const keys: string[] = []
  await page.route('**/api/v1/sessions/*', async (route) => {
    if (route.request().method() !== 'DELETE') return route.continue()
    keys.push(route.request().headers()['idempotency-key'])
    if (!lost) {
      lost = true
      await route.fetch()
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('删除状态尚未确认')
  await expect(page.locator('.user-message')).toHaveCount(0)
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page).toHaveURL(/\/chat$/)
  expect(keys).toHaveLength(2)
  expect(keys[0]).toBe(keys[1])
  await expect(
    other.getByRole('heading', { name: '对话暂不可用' }),
  ).toBeVisible()
  await expect(other.locator('body')).not.toContainText('STEP07删除后不再可见')
  await page.getByText('删除处理记录', { exact: true }).click()
  await expect(page.getByText('本应用在线内容清理完成').first()).toBeVisible()
  await expect(page.locator('body')).not.toContainText('STEP07删除后不再可见')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await screenshot(page, 'deletion-receipt-mobile')
  await page.getByRole('link', { name: '我的', exact: true }).click()
  await page.getByRole('button', { name: '退出账号' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(
    page.getByRole('button', { name: '登录', exact: true }),
  ).toBeVisible()
  await page.goBack()
  await expect(page).toHaveURL(/\/login$/)
  await expect(
    page.getByRole('button', { name: '登录', exact: true }),
  ).toBeVisible()
  await expect(page.locator('body')).not.toContainText('STEP07删除后不再可见')
  await login(page)
  await page.goto(url)
  await expect(
    page.getByRole('heading', { name: '对话暂不可用' }),
  ).toBeVisible()
  await other.close()
})
