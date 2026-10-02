import { expect, test, type Page } from '@playwright/test'

const session = {
  id: 'review-session',
  version: 1,
  title: '合成回归会话',
  title_source: 'manual',
  title_revision: 1,
  title_generation_status: 'not_requested',
  status: 'active',
}
const run = {
  run_id: 'review-run',
  input_id: 'review-input',
  input_text: '合成输入',
  input_version: 1,
  version: 2,
  status: 'completed',
  is_current: true,
  generation: 1,
  last_event_id: '2',
  output: { text: '合成回答' },
}

async function mockChat(page: Page, fontSize = 'normal') {
  await page.route('**/api/v1/**', async (route) => {
    const endpoint = new URL(route.request().url()).pathname
    let json: unknown
    if (endpoint.endsWith('/auth/session'))
      json = {
        user_id: 'review-user',
        email: 'review@example.com',
        csrf_token: 'synthetic',
      }
    else if (endpoint.endsWith('/me/preferences'))
      json = {
        version: 1,
        age_band: 'unknown',
        mode: 'listen',
        display_preferences: {
          font_size: fontSize,
          reduced_motion: true,
          hide_titles: false,
        },
      }
    else if (endpoint.endsWith('/sessions'))
      json = { items: [session], next_cursor: null, has_pending_titles: false }
    else if (endpoint.endsWith('/sessions/' + session.id)) json = session
    else if (endpoint.endsWith('/current-run')) json = run
    else if (endpoint.endsWith('/deletion-preview')) json = { linked_notes: [] }
    else if (endpoint.endsWith('/timeline'))
      json = { items: [run], next_cursor: null }
    else json = { items: [], next_cursor: null }
    await route.fulfill({ json })
  })
  await page.goto('/chat/' + session.id)
  await expect(page.locator('.user-message')).toHaveText(run.input_text)
}

test('a competing tab start restores the active run stop control after draft rejection', async ({
  page,
}) => {
  await mockChat(page)
  let status = 'completed'
  const snapshot = () => ({
    ...run,
    status,
    version: 3,
    output: status === 'completed' ? run.output : null,
  })
  await page.route('**/api/v1/sessions/review-session/current-run', (route) =>
    route.fulfill({ json: snapshot() }),
  )
  await page.route('**/api/v1/run-drafts', async (route) => {
    status = 'running'
    await route.fulfill({ status: 409, json: { code: 'run_active' } })
  })
  await page.route('**/api/v1/runs/review-run', (route) =>
    route.fulfill({ json: snapshot() }),
  )
  await page.route('**/api/v1/runs/review-run/cancel', async (route) => {
    status = 'cancelled'
    await route.fulfill({ json: snapshot() })
  })
  await page.getByLabel('想说的事').fill('another tab accepted first')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await page.getByRole('button', { name: '停止生成', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已停止')
  await expect(page.getByLabel('想说的事')).toHaveValue(
    'another tab accepted first',
  )
})

for (const entry of ['sidebar', 'management']) {
  test(`${entry} deletion stays blocked after a lost response and dialog dismissal`, async ({
    page,
  }) => {
    await mockChat(page)
    const requests: { key: string; body: unknown }[] = []
    let release: () => void = () => {}
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    await page.route('**/api/v1/sessions/' + session.id, async (route) => {
      if (route.request().method() !== 'DELETE') return route.fallback()
      requests.push({
        key: route.request().headers()['idempotency-key'],
        body: route.request().postDataJSON(),
      })
      if (requests.length === 1) {
        await pending
        return route.abort('connectionreset')
      }
      await route.fulfill({
        json: {
          deletion_id: 'synthetic-deletion',
          target: session.id,
          version: 1,
          status: 'completed',
          completed_steps: ['online_blocked', 'messages', 'events'],
          remaining_steps: [],
          retryable: false,
          external_provider_status: 'not_applicable',
        },
      })
    })
    if (entry === 'management')
      await page.getByText('管理此对话', { exact: true }).click()
    const trigger = page.getByRole('button', {
      name: entry === 'sidebar' ? `删除会话：${session.title}` : '删除会话',
      exact: true,
    })
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: '确认删除此会话？' })
    await expect(dialog.getByRole('button', { name: '暂不删除' })).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(
      dialog.getByRole('button', { name: '确认删除', exact: true }),
    ).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(dialog.getByRole('button', { name: '暂不删除' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    await expect(page.locator('.user-message')).toHaveText(run.input_text)
    await trigger.click()
    await dialog.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect.poll(() => requests.length).toBe(1)
    await expect(page.locator('.user-message')).toHaveCount(0)
    await expect(page.locator('.assistant-message')).toHaveCount(0)
    await expect(page.locator('.composer')).toHaveCount(0)
    await page.keyboard.press('Escape')
    await expect(dialog).toBeVisible()
    release()
    await expect(dialog.getByRole('alert')).toContainText('删除状态尚未确认')
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    await expect(page.locator('.composer')).toHaveCount(0)
    await expect(page.locator('.chat-layout')).toContainText('内容已隐藏')
    await trigger.click()
    await dialog.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(page).toHaveURL(/\/chat\/?$/)
    expect(requests).toHaveLength(2)
    expect(requests[0]).toEqual(requests[1])
    expect(requests[0].key).toBeTruthy()
  })
}

test('short viewport keeps an expanded composer send button reachable at both font sizes', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 320, height: 500 })
  const sizes: number[] = []
  for (const fontSize of ['normal', 'large']) {
    await page.unrouteAll()
    await mockChat(page, fontSize)
    const composer = page.getByLabel('想说的事', { exact: true })
    await composer.fill('合成输入\n'.repeat(50))
    await expect(composer).toHaveCSS('height', '200px')
    await expect(composer).toHaveCSS('resize', 'none')
    sizes.push(
      await composer.evaluate((node) =>
        parseFloat(getComputedStyle(node).fontSize),
      ),
    )
    const send = page.getByRole('button', { name: '发送', exact: true })
    await send.scrollIntoViewIfNeeded()
    await expect(send).toBeInViewport({ ratio: 1 })
    await send.click({ trial: true })
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
    await page.screenshot({
      path: testInfo.outputPath(`composer-${fontSize}.png`),
    })
  }
  expect(sizes[0]).toBeCloseTo(15.2)
  expect(sizes[1]).toBeCloseTo(19)
})

test('revision disclosure supports keyboard, retained draft and focus return', async ({
  page,
}) => {
  await mockChat(page)
  const trigger = page.getByRole('button', {
    name: '修订最后输入',
    exact: true,
  })
  const editor = page.getByRole('textbox', { name: '修订内容', exact: true })
  await trigger.focus()
  await trigger.press('Enter')
  await expect(trigger).toHaveAttribute('aria-expanded', 'true')
  await editor.fill('合成修订草稿')
  await editor.press('Escape')
  await expect(editor).toBeHidden()
  await expect(trigger).toBeFocused()
  await trigger.press('Space')
  await expect(editor).toHaveValue('合成修订草稿')
  await page.getByRole('button', { name: '收起修订', exact: true }).click()
  await expect(trigger).toBeFocused()
  await expect(trigger).toHaveAttribute('aria-expanded', 'false')
})

for (const height of [720, 260]) {
  test(`fallback scrolling preserves the timeline pagination anchor at ${height}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height })
    await mockChat(page)
    const turns = Array.from({ length: 21 }, (_, index) => ({
      ...run,
      run_id: `review-run-${String(index).padStart(2, '0')}`,
      input_text: `合成分页输入 ${index}`,
    }))
    await page.route('**/api/v1/**/current-run', (route) =>
      route.fulfill({ json: turns[20] }),
    )
    await page.route('**/api/v1/**/timeline?*', (route) =>
      route.fulfill({
        json: new URL(route.request().url()).searchParams.has('cursor')
          ? { items: [turns[0]], next_cursor: null }
          : { items: turns.slice(1), next_cursor: 'older' },
      }),
    )
    await page.reload()
    await expect(page.locator('.chat-turn')).toHaveCount(20)
    const earlier = page.getByRole('button', { name: '加载更早消息' })
    await earlier.scrollIntoViewIfNeeded()
    const anchor = page.locator('[data-run-id="review-run-01"]')
    const before = await anchor.evaluate(
      (node) => node.getBoundingClientRect().top,
    )
    await earlier.click()
    await expect(page.locator('.chat-turn')).toHaveCount(21)
    const after = await anchor.evaluate(
      (node) => node.getBoundingClientRect().top,
    )
    expect(Math.abs(after - before)).toBeLessThan(2)
  })
}
