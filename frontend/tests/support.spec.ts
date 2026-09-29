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

test('support navigation preserves the shell without flashing the identity check', async ({
  page,
}) => {
  await login(page)
  await expect(page.locator('.support-shell')).toBeVisible()
  // The initial authenticated mount is allowed to replace its loading shell.
  // Observe navigation only after that mount, never compare a null loading box.
  await expect(page.locator('#support-main')).toHaveAttribute(
    'aria-busy',
    'false',
  )
  await expect(
    page.getByRole('heading', { name: '对话', exact: true }),
  ).toBeVisible()
  const monitor = await page.evaluateHandle(() => {
    const shell = document.querySelector('.support-shell')
    const state = { flashed: false, unmounted: false }
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.textContent?.includes('正在确认登录状态'))
            state.flashed = true
        }
        for (const node of record.removedNodes) {
          if (shell && (node === shell || node.contains(shell)))
            state.unmounted = true
        }
      }
    })
    observer.observe(document.body, { childList: true, subtree: true })
    return { state, observer }
  })
  try {
    for (let i = 0; i < 2; i++) {
      const settings = page.getByRole('link', { name: '设置', exact: true })
      const entryBounds = await settings.boundingBox()
      const navBounds = await page.locator('.support-nav').boundingBox()
      expect(entryBounds).not.toBeNull()
      expect(navBounds).not.toBeNull()
      await page.getByRole('link', { name: '设置', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: '设置', exact: true }),
      ).toBeVisible()
      expect(await settings.boundingBox()).toEqual(entryBounds)
      expect(await page.locator('.support-nav').boundingBox()).toEqual(
        navBounds,
      )
      await page.getByRole('link', { name: '账号安全', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: '我的账号', exact: true }),
      ).toBeVisible()
      await page.getByRole('link', { name: '数据管理', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: '对话与数据', exact: true }),
      ).toBeVisible()
      await page.getByRole('link', { name: '支持资源', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: '支持资源', exact: true }),
      ).toBeVisible()
      await page.getByRole('link', { name: '现实支持', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: '暂无已核实的校内值班信息' }),
      ).toBeVisible()
      await page.getByRole('link', { name: '练习', exact: true }).click()
      await page.getByRole('link', { name: '查看练习' }).click()
      await expect(page.getByRole('button', { name: '开始练习' })).toBeVisible()
      await page.getByRole('link', { name: '退出练习，返回资源' }).click()
      await page.getByRole('link', { name: '设置', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: '设置', exact: true }),
      ).toBeVisible()
      await page.getByRole('link', { name: '对话', exact: true }).click()
      await expect(
        page.getByRole('heading', { name: '对话', exact: true }),
      ).toBeVisible()
    }
    expect(await monitor.evaluate(({ state }) => state)).toEqual({
      flashed: false,
      unmounted: false,
    })
  } finally {
    await monitor.evaluate(({ observer }) => observer.disconnect())
    await monitor.dispose()
  }
})

test('direct resource access still requires identity and recovers from identity errors', async ({
  page,
}) => {
  await page.goto('/resources')
  await expect(page).toHaveURL('/login')
  await expect(page.locator('.support-shell')).toHaveCount(0)
  await login(page)
  await page.route('**/api/v1/auth/session', (route) =>
    route.fulfill({ status: 503, json: { code: 'unavailable' } }),
  )
  await page.goto('/resources')
  await expect(page.getByRole('alert')).toHaveText(
    '无法确认登录状态，内容已隐藏。',
  )
  await expect(page.locator('.support-shell')).toHaveCount(0)
  await page.unroute('**/api/v1/auth/session')
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: '支持资源', exact: true }),
  ).toBeVisible()
})

test('multi-turn timeline: pagination, reload, switching and mobile sidebar', async ({
  page,
}) => {
  // This journey includes 21 sequential worker replies plus reloads and screenshots.
  test.setTimeout(180000)
  await login(page, 'admin@example.com', 'synthetic-admin-password')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  const inputs = Array.from(
    { length: 21 },
    (_, index) => `合成分页输入 ${index + 1}：纸船与河岸`,
  )
  for (const text of inputs) {
    await page.getByLabel('想说的事').fill(text)
    await page.getByRole('button', { name: '发送', exact: true }).click()
    await expect(page.getByRole('status')).toContainText('已完成', {
      timeout: 20000,
    })
    await expect(page.locator('.user-message').last()).toHaveText(text)
  }
  const url = page.url()
  await page.reload()
  await expect(page.locator('.user-message')).toHaveCount(20)
  const earlier = page.getByRole('button', { name: '加载更早消息' })
  await earlier.scrollIntoViewIfNeeded()
  const anchor = page.locator('.chat-turn').first()
  const anchorId = await anchor.getAttribute('data-run-id')
  const anchorTop = await anchor.evaluate(
    (node) => node.getBoundingClientRect().top,
  )
  const olderResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/timeline?') &&
      response.url().includes('cursor='),
  )
  await earlier.click()
  const olderPage = await (await olderResponse).json()
  expect(
    olderPage.items.map((item: { input_text: string }) => item.input_text),
  ).toEqual([inputs[0]])
  await expect(page.locator('.user-message')).toHaveText(inputs)
  await expect(page.locator('.assistant-message')).toHaveCount(21)
  expect(
    Math.abs(
      (await page
        .locator(`[data-run-id="${anchorId}"]`)
        .evaluate((node) => node.getBoundingClientRect().top)) - anchorTop,
    ),
  ).toBeLessThan(2)
  await expect(page.getByText('查看旧版本', { exact: true })).toHaveCount(0)
  await screenshot(page, 'multiturn-desktop')
  await page.getByRole('button', { name: '新建对话', exact: true }).click()
  await expect(page).not.toHaveURL(url)
  await expect(page.locator('.user-message')).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(
    page.getByRole('complementary', { name: '会话列表' }),
  ).toBeHidden()
  await page.getByRole('button', { name: '历史对话', exact: true }).click()
  await expect(
    page.getByRole('complementary', { name: '会话列表' }),
  ).toBeVisible()
  await page.locator(`.session-list a[href="${new URL(url).pathname}"]`).click()
  await expect(page).toHaveURL(url)
  await expect(
    page.getByRole('complementary', { name: '会话列表' }),
  ).toBeHidden()
  // Returning to the same session retains pages already loaded in Query.
  await expect(page.locator('.user-message')).toHaveCount(21)
  await screenshot(page, 'multiturn-mobile')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  // Exceeds the unchanged fake envelope, producing a real persisted failure.
  const oversized = '合成'.repeat(2000)
  await page.getByLabel('想说的事').fill(oversized)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('本次响应失败', {
    timeout: 20000,
  })
  await expect(page.locator('.user-message').last()).toHaveText(oversized)
  await expect(
    page
      .locator('.chat-turn')
      .last()
      .getByRole('button', { name: '重新生成', exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '查询运行状态' })).toHaveCount(
    0,
  )
  await expect(
    page.locator('.chat-turn').last().locator('.assistant-message'),
  ).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('status')).toContainText('本次响应失败')
  await expect(page.locator('.user-message').last()).toHaveText(oversized)
})

test('chat: real send, lost acknowledgement retry, snapshot reload, account isolation', async ({
  page,
  context,
}) => {
  await login(page)
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
  await expect(page.locator('.chat-title')).toHaveText('合成对话主题', {
    timeout: 20000,
  })
  const text = await page.locator('.assistant-message').innerText()
  const url = page.url()
  await page.reload()
  await expect(page.locator('.chat-title')).toHaveText('合成对话主题')
  await expect(page.locator('.assistant-message')).toHaveText(text)
  await screenshot(page, 'chat-desktop')
  await page.getByRole('link', { name: '← 返回对话列表' }).click()
  await page.getByLabel('搜索标题').fill('合成对话主题')
  await page.getByLabel('搜索标题').press('Enter')
  await page.locator(`.session-list a[href="${new URL(url).pathname}"]`).click()
  await expect(page).toHaveURL(url)
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

test('unaccepted send reports its unchanged state and retries the original message', async ({
  page,
}) => {
  await login(page, 'admin@example.com', 'synthetic-admin-password')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await page.getByLabel('想说的事').fill('合成未接收消息')
  await page.route('**/api/v1/runs/*/start', (route) => route.abort('failed'))
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('发送未确认')
  await page.getByRole('button', { name: '检查发送状态' }).click()
  await expect(
    page.getByText('尚未确认发送成功。请点击“重试原消息”继续发送。', {
      exact: true,
    }),
  ).toBeVisible()
  await expect(page.getByLabel('想说的事')).toHaveValue('合成未接收消息')
  await page.unroute('**/api/v1/runs/*/start')
  await page.getByRole('button', { name: '重试原消息', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await expect(page.locator('.user-message')).toHaveText(['合成未接收消息'])
  await expect(page.getByRole('button', { name: '检查发送状态' })).toHaveCount(
    0,
  )
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
  await page.getByRole('button', { name: '检查发送状态' }).click()
  await expect(page.getByRole('status')).toContainText('已完成', {
    timeout: 20000,
  })
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByLabel('想说的事')).toHaveValue(
    '合成状态查询后的新输入',
  )
  expect(starts).toBe(1)
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.locator('.user-message')).toHaveText([
    '合成状态查询前的输入',
    '合成状态查询后的新输入',
  ])
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
  await page.reload()
  await expect(page.locator('.user-message')).toHaveText('合成取消检查')
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
  await expect(page.getByLabel('想说的事')).toBeEnabled()
  await page.getByLabel('想说的事').focus()
  await page.keyboard.type('synthetic keyboard')
  await expect(
    page.getByRole('button', { name: '发送', exact: true }),
  ).toBeEnabled()
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

test('navigation keeps core entry clear, settings drafts and exercise return accessible', async ({
  page,
}) => {
  const writes: string[] = []
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      /\/sessions$|\/run-drafts|\/runs\//.test(request.url())
    )
      writes.push(request.url())
  })
  await login(page, 'step05-browser@example.com')
  await expect(
    page.getByRole('heading', { name: '对话', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('navigation', { name: '主要导航' }).getByRole('link'),
  ).toHaveCount(2)
  await expect(
    page.getByRole('link', { name: '对话', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  expect(writes).toEqual([])
  await page.goto('/')
  await expect(page).toHaveURL('/chat')
  await expect(page.getByRole('button', { name: '开始一次对话' })).toBeEnabled()
  await screenshot(page, 'navigation-home-desktop')
  await page.getByRole('link', { name: '设置', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: '交流与显示偏好' }),
  ).toBeVisible()
  await page.getByRole('link', { name: '账号安全', exact: true }).click()
  await page.getByLabel('当前密码').fill('unsaved-local-draft')
  await page.getByRole('link', { name: '数据管理', exact: true }).click()
  await expect(page.getByLabel('当前密码')).not.toBeVisible()
  await page.goBack()
  await expect(page.getByLabel('当前密码')).toHaveValue('unsaved-local-draft')
  await page.goForward()
  await page.reload()
  await expect(
    page.getByRole('link', { name: '数据管理', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await expect(
    page.getByRole('link', { name: '设置', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
  await screenshot(page, 'navigation-settings-desktop')
  await page.getByRole('link', { name: '管理和删除会话 →' }).click()
  await page.getByLabel('搜索标题').fill('没有匹配的合成标题-navigation')
  await page.getByLabel('搜索标题').press('Enter')
  await expect(page.getByText('没有匹配的对话。')).toBeVisible()
  await page.getByRole('button', { name: '开始一次对话' }).click()
  await expect(page).toHaveURL(/\/chat\/.+/)
  const conversationUrl = page.url()
  await expect(page.getByRole('region', { name: '我的对话' })).toBeVisible()
  await expect(page.getByLabel('对话标题')).not.toBeVisible()
  await page.getByText('管理此对话', { exact: true }).click()
  const title = '用于检查窄屏换行的合成对话标题'.repeat(5)
  await page.getByLabel('对话标题').fill(title)
  await page.getByRole('button', { name: '保存标题' }).click()
  await expect(page.getByRole('heading', { name: title })).toBeVisible()
  await page.getByText('管理此对话', { exact: true }).click()
  await page.setViewportSize({ width: 375, height: 812 })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await screenshot(page, 'navigation-long-title-mobile')
  await page.getByRole('link', { name: '独立练习' }).click()
  await page.getByRole('link', { name: '退出练习，返回对话' }).click()
  await expect(page).toHaveURL(conversationUrl)
  await page.getByRole('link', { name: '独立练习' }).click()
  await page.getByRole('button', { name: '开始练习' }).click()
  for (let i = 0; i < 3; i++)
    await page.getByRole('button', { name: '下一步' }).click()
  await page.getByRole('link', { name: '返回原对话' }).click()
  await expect(page).toHaveURL(conversationUrl)
  expect(writes).toHaveLength(1)
  await page.getByRole('link', { name: '设置', exact: true }).click()
  await expect(page).toHaveURL(/\/me\?section=preferences/)
  await expect(page.getByRole('heading', { name: '设置' })).toBeVisible()
  await page
    .getByRole('combobox', { name: '字号', exact: true })
    .selectOption('large')
  await page.getByRole('button', { name: '保存偏好' }).click()
  await expect(page.locator('.support-shell')).toHaveAttribute(
    'data-large',
    'true',
  )
  await screenshot(page, 'navigation-settings-mobile')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.getByRole('link', { name: '账号安全', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('heading', { name: '我的账号' })).toBeVisible()
  await page.getByRole('link', { name: '交流与显示', exact: true }).click()
  await page
    .getByRole('combobox', { name: '字号', exact: true })
    .selectOption('normal')
  await page.getByRole('button', { name: '保存偏好' }).click()
  await expect(page.locator('.support-shell')).toHaveAttribute(
    'data-large',
    'false',
  )
})
