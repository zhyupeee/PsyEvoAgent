import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

async function snapshotOf(page: Page, id: string) {
  return page.evaluate(async (runId) => {
    const result = await fetch(`/api/v1/runs/${runId}`)
    if (!result.ok) throw new Error(`snapshot status ${result.status}`)
    return result.json() as Promise<{
      output: { text: string } | null
      status: string
      budget_used: { calls: number }
      version_binding: { model_ref: string }
      budget: { max_cost: string | null }
    }>
  }, id)
}

async function login(page: Page, email = 'step08-live@example.com') {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page
    .getByLabel('密码', { exact: true })
    .fill('synthetic-browser-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/chat')
  expect(
    await page.evaluate(
      async () =>
        (
          await (
            await fetch('/api/v1/auth/session', { credentials: 'same-origin' })
          ).json()
        ).email,
    ),
  ).toBe(email)
}

test('live full-buffer journey: send, SSE, reload, isolation, cancel and confirmed deletion', async ({
  page,
  context,
}) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort(),
  )
  await login(page)
  await page.goto('/chat')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  // Keep the existing paid gate at its original two support calls.
  // Automatic title quality needs a separate explicit live verification.
  await page.getByText('管理此对话', { exact: true }).click()
  await page.getByLabel('对话标题').fill('整稿合成验证')
  await page.getByRole('button', { name: '保存标题' }).click()
  await expect(page.locator('.chat-title')).toHaveText('整稿合成验证')
  await page.getByText('管理此对话', { exact: true }).click()
  await page
    .getByLabel('想说的事')
    .fill('这是独立合成测试：今天学习有点累，我只想说说，不需要建议。')
  const started = page.waitForResponse(
    (r) =>
      /\/runs\/[^/]+\/start$/.test(r.url()) && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const run: { run_id: string } = await (await started).json()
  const streamResult = page.evaluate(
    (id) =>
      new Promise<{ text: string; deltas: number }>((resolve, reject) => {
        const events = new EventSource(`/api/v1/runs/${id}/events`)
        const pieces = new Map<number, string>()
        const timeout = setTimeout(() => {
          events.close()
          reject(new Error('SSE timeout'))
        }, 125000)
        events.addEventListener('message.delta', (event) => {
          const envelope = JSON.parse((event as MessageEvent<string>).data)
          pieces.set(Number(envelope.event_id), envelope.payload.text)
        })
        events.addEventListener('run.completed', () => {
          clearTimeout(timeout)
          events.close()
          resolve({
            text: [...pieces]
              .sort((a, b) => a[0] - b[0])
              .map((p) => p[1])
              .join(''),
            deltas: pieces.size,
          })
        })
        events.addEventListener('run.failed', () => {
          clearTimeout(timeout)
          events.close()
          reject(new Error('Live run failed'))
        })
      }),
    run.run_id,
  )
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 125000,
  })
  const stream = await streamResult
  expect(stream.deltas).toBe(1)
  await expect(page.locator('.assistant-message')).toHaveText(stream.text)
  expect(stream.text.length).toBeGreaterThan(0)
  const url = page.url()
  const sessionId = url.split('/').pop()!
  await page.reload()
  await expect(page.locator('.assistant-message')).toHaveText(stream.text)
  const snapshot = await snapshotOf(page, run.run_id)
  expect(snapshot.output?.text).toBe(stream.text)
  expect(snapshot.budget_used.calls).toBe(1)
  expect(snapshot.version_binding.model_ref).toBe('grok-4.7')
  expect(snapshot.budget.max_cost).toBeNull()
  await page.screenshot({
    path: path.join(process.env.PSYEVO_STEP08_ARTIFACTS!, 'live-chat.png'),
    fullPage: true,
  })

  const other = await context
    .browser()!
    .newContext({ baseURL: new URL(url).origin })
  const otherPage = await other.newPage()
  await login(otherPage, 'step08-other@example.com')
  expect(
    await otherPage.evaluate(
      async (id) => (await fetch(`/api/v1/runs/${id}`)).status,
      run.run_id,
    ),
  ).toBe(404)
  await other.close()

  await page
    .getByLabel('想说的事')
    .fill('这是第二条合成测试消息：请倾听我今天的学习感受。')
  const secondStarted = page.waitForResponse(
    (r) =>
      /\/runs\/[^/]+\/start$/.test(r.url()) && r.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const cancelled: { run_id: string } = await (await secondStarted).json()
  await expect
    .poll(
      async () => (await snapshotOf(page, cancelled.run_id)).budget_used.calls,
    )
    .toBe(1)
  await page.getByRole('button', { name: '停止生成' }).click()
  await expect(page.getByRole('status')).toContainText('已停止')
  await page.reload()
  await expect(page.getByRole('status')).toContainText('已停止')
  const cancelledSnapshot = await snapshotOf(page, cancelled.run_id)
  expect(cancelledSnapshot.status).toBe('cancelled')
  expect(cancelledSnapshot.output).toBeNull()

  await page.getByText('管理此对话', { exact: true }).click()
  await page.getByRole('button', { name: '删除会话', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page).toHaveURL(/\/chat$/)
  await page.getByRole('link', { name: '删除处理记录', exact: true }).click()
  await expect(page).toHaveURL('/me?section=data')
  await page.getByText('删除处理记录', { exact: true }).click()
  await expect(
    page.getByText(
      '模型服务商的数据保留及删除状态未知，本回执仅确认本应用在线清理。',
    ),
  ).toBeVisible()
  expect(
    await page.evaluate(
      async (id) => (await fetch(`/api/v1/runs/${id}`)).status,
      run.run_id,
    ),
  ).toBe(404)
  const dir = process.env.PSYEVO_STEP08_ARTIFACTS!
  await page.screenshot({
    path: path.join(dir, 'live-deletion.png'),
    fullPage: true,
  })
  await fs.writeFile(
    path.join(dir, 'live-browser.json'),
    JSON.stringify(
      {
        run_id: run.run_id,
        cancelled_run_id: cancelled.run_id,
        session_id: sessionId,
        delta_count: stream.deltas,
        sse_snapshot_dom_equal: true,
        refreshed_call_count: snapshot.budget_used.calls,
      },
      null,
      2,
    ),
  )
})
