import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

async function login(page: Page, email = 's2-records-browser@example.com') {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page
    .getByLabel('密码', { exact: true })
    .fill('synthetic-browser-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/chat')
}

async function note(
  page: Page,
  title: string,
  body = '合成笔记：先把一件事写下来。',
) {
  await page.goto('/records')
  await page.getByRole('button', { name: '新建笔记' }).click()
  await page.getByLabel('标题（可选）').fill(title)
  await page.getByLabel('正文', { exact: true }).fill(body)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: title, exact: true }),
  ).toBeVisible()
}

async function shot(page: Page, name: string) {
  const directory = process.env.PSYEVO_S2_STEP02_ARTIFACTS
  if (!directory) throw new Error('Missing records evidence directory')
  await page.screenshot({
    path: path.join(directory, name + '.png'),
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
}

test.beforeEach(async ({ context }) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
})

test('S2-A01 note persists after reopening, filters, edits and confirms deletion', async ({
  page,
}) => {
  await login(page)
  const title = `S2 持久笔记 ${Date.now()}`
  await note(page, title)
  await shot(page, 'records-desktop')
  await page.reload()
  await page.getByRole('button', { name: title }).click()
  await expect(page.getByText('合成笔记：先把一件事写下来。')).toBeVisible()
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByLabel('正文', { exact: true }).fill('合成修订内容')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('合成修订内容', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '暂不删除' }).click()
  await expect(page.getByText('合成修订内容', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page.getByRole('button', { name: title })).toHaveCount(0)
})

test('S2-A01 failed draft save keeps editor and lost acknowledgement is reconciled', async ({
  page,
}) => {
  await login(page)
  await page.goto('/records')
  await page.getByRole('button', { name: '新建笔记' }).click()
  const title = `S2 草稿 ${Date.now()}`
  await page.getByLabel('标题（可选）').fill(title)
  await page.getByLabel('正文', { exact: true }).fill('不能丢失的合成草稿')
  await page.getByRole('combobox', { name: '保存状态' }).click()
  await page.getByRole('option', { name: '草稿', exact: true }).click()
  await page.route('**/api/v1/notes', async (route) => {
    if (route.request().method() === 'POST')
      await route.fulfill({ status: 503, json: { code: 'synthetic_failure' } })
    else await route.continue()
  })
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByLabel('正文', { exact: true })).toHaveValue(
    '不能丢失的合成草稿',
  )
  await page.unroute('**/api/v1/notes')
  await page.route('**/api/v1/notes', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fetch()
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('button', { name: '核对保存结果' })).toBeVisible()
  await page.getByRole('button', { name: '核对保存结果' }).click()
  await expect(page.getByRole('heading', { name: title })).toBeVisible()
  await expect(
    page.getByRole('button', { name: '带入本次对话' }),
  ).toBeDisabled()
  await expect(page.getByRole('button', { name: title })).toHaveCount(1)
})

test('S2-A01 dirty navigation needs explicit discard and no localStorage body', async ({
  page,
}) => {
  await login(page)
  await page.goto('/records')
  await page.getByRole('button', { name: '新建笔记' }).click()
  await page.getByLabel('正文', { exact: true }).fill('PRIVATE-DRAFT-S2')
  await page.getByRole('link', { name: '睡眠', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('放弃未保存')
  await page.getByRole('button', { name: '继续编辑' }).click()
  await expect(page.getByLabel('正文', { exact: true })).toHaveValue(
    'PRIVATE-DRAFT-S2',
  )
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain(
    'PRIVATE-DRAFT-S2',
  )
  await page.getByRole('link', { name: '睡眠', exact: true }).click()
  await page.getByRole('button', { name: '放弃修改' }).click()
  await expect(page).toHaveURL('/records/sleep')
})

for (const kind of ['new-note', 'edit-note', 'sleep', 'support-card']) {
  test(`save reconciliation preserves newer ${kind} edits and updates the same record`, async ({
    page,
  }) => {
    await login(page)
    const title = `S2 恢复 ${kind} ${Date.now()}`
    const field =
      kind === 'support-card'
        ? '想提醒自己的话'
        : kind === 'sleep'
          ? '主观感受（可选）'
          : '正文'
    const endpoint =
      kind === 'support-card'
        ? '/support-card'
        : kind === 'sleep'
          ? '/sleep-records'
          : '/notes'
    if (kind === 'support-card') await page.goto('/me/support-card')
    else if (kind === 'sleep') {
      await page.goto('/records/sleep')
      await page.getByRole('button', { name: '记录睡眠', exact: true }).click()
      await page.getByLabel('记录日期', { exact: true }).fill('2026-09-30')
    } else if (kind === 'edit-note') {
      await note(page, title)
      await page.getByRole('button', { name: '编辑', exact: true }).click()
    } else {
      await page.goto('/records')
      await page.getByRole('button', { name: '新建笔记' }).click()
      await page.getByLabel('标题（可选）').fill(title)
    }
    await page.getByLabel(field, { exact: true }).fill('提交的合成内容 A')
    let savedId = ''
    let savedVersion = 0
    let writes = 0
    await page.route(`**/api/v1${endpoint}**`, async (route) => {
      if (!['POST', 'PATCH', 'PUT'].includes(route.request().method()))
        return route.continue()
      writes++
      if (writes !== 1) return route.continue()
      const response = await route.fetch()
      expect(response.ok()).toBe(true)
      const saved = await response.json()
      savedId = saved.id
      savedVersion = saved.version
      await route.abort('failed')
    })
    await page.getByRole('button', { name: '保存', exact: true }).click()
    await expect(
      page.getByRole('button', { name: '核对保存结果' }),
    ).toBeVisible()
    await page.getByLabel(field, { exact: true }).fill('后来编辑的合成内容 B')
    await page.getByRole('button', { name: '核对保存结果' }).click()
    await expect(page.getByRole('status')).toContainText('之后的编辑仍未保存')
    await expect(page.getByLabel(field, { exact: true })).toHaveValue(
      '后来编辑的合成内容 B',
    )
    if (kind === 'new-note') {
      await page.getByRole('link', { name: '睡眠', exact: true }).click()
      await expect(page.getByRole('dialog')).toContainText('放弃未保存')
      await page.getByRole('button', { name: '继续编辑' }).click()
    }
    const update = page.waitForResponse(
      (response) =>
        ['PATCH', 'PUT'].includes(response.request().method()) &&
        response.url().includes(endpoint),
    )
    await page.getByRole('button', { name: '保存', exact: true }).click()
    const response = await update
    expect(response.ok()).toBe(true)
    expect(response.request().postDataJSON().expected_version).toBe(
      savedVersion,
    )
    const saved = await response.json()
    expect(saved.id).toBe(savedId)
    expect(saved.version).toBe(savedVersion + 1)
    expect(
      saved[
        kind === 'support-card'
          ? 'self_reminders'
          : kind === 'sleep'
            ? 'feeling'
            : 'body'
      ],
    ).toBe('后来编辑的合成内容 B')
    expect(writes).toBe(2)
    await expect(
      page.getByRole('button', { name: '核对保存结果' }),
    ).toHaveCount(0)
  })
}

test('edits made while a successful save response is pending remain unsaved', async ({
  page,
}) => {
  await login(page)
  await page.goto('/records')
  await page.getByRole('button', { name: '新建笔记' }).click()
  await page.getByLabel('正文', { exact: true }).fill('提交的合成内容 A')
  let release: () => void = () => {}
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  let committed = false
  await page.route('**/api/v1/notes', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    const response = await route.fetch()
    committed = true
    await pending
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect.poll(() => committed).toBe(true)
  // Only the save status changes, so snapshot checks must include it too.
  await page.getByRole('combobox', { name: '保存状态' }).click()
  await page.getByRole('option', { name: '草稿', exact: true }).click()
  release()
  await expect(page.getByRole('status')).toContainText('之后的编辑仍未保存')
  await expect(page.getByRole('combobox', { name: '保存状态' })).toContainText(
    '草稿',
  )
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(
    page.getByRole('button', { name: '带入本次对话' }),
  ).toBeDisabled()
})

test('accepted lost send consumes the selected record only once', async ({
  page,
}) => {
  await login(page)
  await note(page, `S2 单轮恢复 ${Date.now()}`)
  await page.getByRole('button', { name: '带入本次对话' }).click()
  await expect(page.getByText(/本次参考/)).toBeVisible()
  const grants: string[][] = []
  await page.route('**/api/v1/runs/*/start', async (route) => {
    grants.push(route.request().postDataJSON().grant_ids)
    if (grants.length === 1) {
      await route.fetch()
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByLabel('想说的事').fill('合成：本轮参考这条笔记。')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('发送未确认')
  await expect(
    page.getByRole('button', { name: '移除', exact: true }),
  ).toBeDisabled()
  await page.getByLabel('想说的事').fill('合成：下一轮新内容。')
  await page.getByRole('button', { name: '检查发送状态' }).click()
  await expect(page.getByText(/本次参考/)).toHaveCount(0)
  await expect(page).toHaveURL(/\/chat\/[^?]+$/)
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await expect(page.getByLabel('想说的事')).toHaveValue('合成：下一轮新内容。')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect.poll(() => grants.length).toBe(2)
  await expect(page.locator('.user-message')).toHaveCount(2)
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  expect(grants.map((ids) => ids.length)).toEqual([2, 1])
})

test('a deleted selected record can be removed after its grant returns 404', async ({
  page,
}) => {
  await login(page)
  await note(page, `S2 已删除附件 ${Date.now()}`)
  await page.getByRole('button', { name: '带入本次对话' }).click()
  await expect(page.getByText(/本次参考/)).toBeVisible()
  const recordId = new URL(page.url()).searchParams.get('record')!
  await page.evaluate(async (id) => {
    const { csrf_token } = await (await fetch('/api/v1/auth/session')).json()
    const { version } = await (await fetch(`/api/v1/notes/${id}`)).json()
    const response = await fetch(`/api/v1/notes/${id}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf_token,
        'Idempotency-Key': crypto.randomUUID(),
      },
      body: JSON.stringify({ expected_version: version, confirmed: true }),
    })
    if (!response.ok) throw new Error('Synthetic record deletion failed')
  }, recordId)
  await page.getByLabel('想说的事').fill('合成：移除后继续对话。')
  const rejection = page.waitForResponse(
    (response) =>
      response.url().endsWith('/context-grants') && response.status() === 404,
  )
  await page.getByRole('button', { name: '发送', exact: true }).click()
  expect((await (await rejection).json()).code).toBe('not_found')
  await page.getByRole('button', { name: '移除', exact: true }).click()
  await expect(page.getByText(/本次参考/)).toHaveCount(0)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
})

test('reopening deletion waits for a fresh preview and blocks confirmation on preview failure', async ({
  page,
}) => {
  await login(page)
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await page.getByLabel('想说的事').fill('合成：删除预览的摘记来源。')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await page.getByText('管理此对话', { exact: true }).click()
  const trigger = page
    .locator('.session-actions')
    .getByRole('button', { name: '删除会话' })
  const dialog = page.getByRole('dialog')
  await trigger.click()
  await expect(dialog).toContainText('一并删除的关联摘记：无')
  await dialog.getByRole('button', { name: '暂不删除' }).click()
  // Create through the actual API while keeping this page's Query cache alive.
  const title = `S2 新关联摘记 ${Date.now()}`
  await page.evaluate(async (title) => {
    const { csrf_token } = await (await fetch('/api/v1/auth/session')).json()
    const id = location.pathname.split('/').at(-1)
    const run = await (await fetch(`/api/v1/sessions/${id}/current-run`)).json()
    const response = await fetch('/api/v1/notes', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf_token,
        'Idempotency-Key': crypto.randomUUID(),
      },
      body: JSON.stringify({
        kind: 'linked_excerpt',
        title,
        source_refs: [
          {
            source_type: 'message',
            source_id: run.input_id,
            source_version: run.input_version,
          },
        ],
      }),
    })
    if (!response.ok) throw new Error('Synthetic excerpt creation failed')
  }, title)
  let release: () => void = () => {}
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  let previews = 0
  await page.route('**/api/v1/sessions/*/deletion-preview', async (route) => {
    previews++
    if (previews === 1) {
      await pending
      await route.continue()
    } else
      await route.fulfill({ status: 503, json: { code: 'synthetic_failure' } })
  })
  await trigger.click()
  await expect(dialog.getByRole('status')).toContainText('正在核对')
  await expect(
    dialog.getByRole('button', { name: '确认删除', exact: true }),
  ).toBeDisabled()
  release()
  await expect(dialog).toContainText(title)
  await expect(
    dialog.getByRole('button', { name: '确认删除', exact: true }),
  ).toBeEnabled()
  await dialog.getByRole('button', { name: '暂不删除' }).click()
  await trigger.click()
  await expect(dialog.getByRole('alert')).toContainText('暂时无法核对')
  await expect(
    dialog.getByRole('button', { name: '确认删除', exact: true }),
  ).toBeDisabled()
  expect(previews).toBe(2)
})

test('S2-A02 cross-day and unknown times, server data after login on mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page)
  await page.goto('/records/sleep')
  await page.getByRole('button', { name: '记录睡眠', exact: true }).click()
  await page.getByLabel('记录日期', { exact: true }).fill('2026-09-30')
  await expect(page.getByLabel('入睡时间', { exact: false })).toHaveValue('')
  await page
    .getByLabel('入睡时间', { exact: false })
    .fill('2026-09-29T23:30:00+08:00')
  await page
    .getByLabel('起床时间', { exact: false })
    .fill('2026-09-30T07:00:00+08:00')
  await page.getByLabel('时区（如 Asia/Shanghai）').fill('Asia/Shanghai')
  await page.getByLabel('主观感受（可选）').fill('合成：醒来时有些困')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('450 分钟（不是实际睡眠时长）')).toBeVisible()
  await shot(page, 'sleep-mobile')
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByLabel('起床时间', { exact: false }).fill('')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('起止不完整，暂不计算')).toBeVisible()
  await page.reload()
  await page
    .getByRole('button', { name: '2026-09-30 合成：醒来时有些困' })
    .click()
  await expect(page.getByText('起止不完整，暂不计算')).toBeVisible()
})

test('S2-A03 optional fields, conflict preserves edits, compare and clear', async ({
  page,
  context,
}) => {
  await login(page)
  await page.goto('/me/support-card')
  await page
    .getByLabel('对我有帮助的方法', { exact: true })
    .fill('合成方法：先写下来')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(
    page.getByRole('button', { name: '清空', exact: true }),
  ).toBeEnabled()
  const second = await context.newPage()
  await second.goto('/me/support-card')
  await expect(
    second.getByLabel('对我有帮助的方法', { exact: true }),
  ).toHaveValue('合成方法：先写下来')
  await page
    .getByLabel('想提醒自己的话', { exact: true })
    .fill('本页待保存内容')
  await second
    .getByLabel('想提醒自己的话', { exact: true })
    .fill('另一处已保存内容')
  await second.getByRole('button', { name: '保存', exact: true }).click()
  await expect(
    second.getByRole('button', { name: '查看旧版本差异' }),
  ).toBeEnabled()
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('版本冲突')
  await expect(page.getByLabel('想提醒自己的话', { exact: true })).toHaveValue(
    '本页待保存内容',
  )
  await expect(
    page.getByText('另一处已保存内容', { exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: '已核对，保留我的编辑继续' }).click()
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(
    page.getByRole('button', { name: '保存', exact: true }),
  ).toBeEnabled()
  await page
    .getByRole('heading', { name: '支持备忘卡', exact: true })
    .scrollIntoViewIfNeeded()
  await shot(page, 'support-card-desktop')
  await page.getByRole('button', { name: '查看旧版本差异' }).click()
  await expect(page.getByRole('dialog')).toContainText('另一处已保存内容')
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '清空', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(
    page.getByLabel('对我有帮助的方法', { exact: true }),
  ).toHaveValue('')
  await expect(page.getByLabel('想提醒自己的话', { exact: true })).toHaveValue(
    '',
  )
  await second.close()
})

test('S2-A01 excerpt preview, one-turn grant and source deletion', async ({
  page,
}) => {
  await login(page)
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await page.getByLabel('想说的事').fill('合成摘记来源：今天完成了一件小事。')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  const sourceUrl = page.url()
  await page
    .getByRole('button', { name: '加入笔记', exact: true })
    .last()
    .click()
  await expect(page.getByRole('dialog')).toContainText('合成摘记来源')
  const title = `S2 摘记 ${Date.now()}`
  await page.getByLabel('标题（可选）').fill(title)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page).toHaveURL('/records')
  await page.getByRole('button', { name: title }).click()
  await page.getByRole('button', { name: '带入本次对话' }).click()
  await expect(page.getByText(/本次参考/)).toContainText(title)
  await page.getByLabel('想说的事').fill('请听我说说这件事。')
  const start = page.waitForRequest(
    (request) =>
      request.url().endsWith('/start') && request.method() === 'POST',
  )
  await page.getByRole('button', { name: '发送', exact: true }).click()
  expect((await start).postDataJSON().grant_ids).toHaveLength(2)
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await expect(page.getByText(/本次参考/)).toHaveCount(0)
  await page.goto(sourceUrl)
  await page.getByText('管理此对话', { exact: true }).click()
  await page
    .locator('.session-actions')
    .getByRole('button', { name: '删除会话' })
    .click()
  await expect(page.getByRole('dialog')).toContainText(title)
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await page.goto('/records')
  await expect(page.getByRole('button', { name: title })).toHaveCount(0)
})
