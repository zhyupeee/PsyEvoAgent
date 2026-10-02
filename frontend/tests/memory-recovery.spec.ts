import { expect, test, type Page } from '@playwright/test'

async function fixture(page: Page) {
  let row = {
    id: 'synthetic-memory',
    version: 1,
    content: '合成记忆：我喜欢散步。',
    claim_type: 'user_statement',
    status: 'active',
    event_time: null,
    recorded_at: '2026-10-02T00:00:00Z',
    source_refs: [
      { source_type: 'note', source_id: 'synthetic-note', source_version: 1 },
    ],
    source_available: true,
  }
  let deleted = false
  const attempts: { version: number; key: string | undefined }[] = []
  await page
    .context()
    .route('**/*', (route) =>
      new URL(route.request().url()).hostname === '127.0.0.1'
        ? route.continue()
        : route.abort('blockedbyclient'),
    )
  await page.route('**/api/v1/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    if (url.pathname.endsWith('/auth/session'))
      return route.fulfill({
        json: {
          user_id: 'synthetic',
          email: 'memory@example.com',
          csrf_token: 'synthetic',
        },
      })
    if (url.pathname.endsWith('/me/preferences'))
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
    if (url.pathname.endsWith('/memories'))
      return route.fulfill({
        json: {
          items:
            !deleted && row.status === url.searchParams.get('status')
              ? [row]
              : [],
          next_cursor: null,
        },
      })
    if (url.pathname.endsWith('/deletion-preview'))
      return route.fulfill({
        json: {
          memory_id: row.id,
          version: row.version,
          delete_original: false,
          source_refs: row.source_refs,
        },
      })
    if (url.pathname.endsWith('/memories/' + row.id)) {
      if (req.method() === 'GET') return route.fulfill({ json: row })
      const body = req.postDataJSON()
      attempts.push({
        version: body.expected_version,
        key: req.headers()['idempotency-key'],
      })
      if (body.expected_version !== row.version)
        return route.fulfill({
          status: 409,
          json: { code: 'version_conflict' },
        })
      if (req.method() === 'DELETE') {
        expect(body.confirmed).toBe(true)
        deleted = true
        return route.fulfill({
          json: { deletion_id: 'synthetic-deletion', status: 'completed' },
        })
      }
      row = { ...row, ...body, version: row.version + 1 }
      return route.fulfill({ json: row })
    }
    return route.fulfill({
      status: 503,
      json: { code: 'synthetic_unavailable' },
    })
  })
  await page.goto('/me/memories')
  await expect(page.getByRole('heading', { name: row.content })).toBeVisible()
  return {
    attempts,
    update: (sourceAvailable = true) => {
      row = {
        ...row,
        version: row.version + 1,
        content: '另一窗口已更新的合成记忆',
        source_available: sourceAvailable,
      }
    },
  }
}

for (const action of ['更正', '停止使用', '遗忘']) {
  test(`memory ${action} restores keyboard focus after Escape and cancellation`, async ({
    page,
  }) => {
    await fixture(page)
    const opener = page.getByRole('button', { name: action, exact: true })
    for (const escape of [true, false]) {
      await opener.focus()
      await page.keyboard.press('Enter')
      await expect(page.getByRole('dialog')).toBeVisible()
      if (escape) await page.keyboard.press('Escape')
      else await page.getByRole('button', { name: '取消', exact: true }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(opener).toBeFocused()
    }
  })
}

test('dirty memory correction returns to editor, then restores opener when discarded', async ({
  page,
}) => {
  await fixture(page)
  const opener = page.getByRole('button', { name: '更正', exact: true })
  await opener.focus()
  await page.keyboard.press('Enter')
  const editor = page.getByLabel('更正内容')
  await editor.fill('未保存的合成更正')
  for (const escape of [true, false]) {
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog').last()).toContainText('放弃未保存')
    if (escape) await page.keyboard.press('Escape')
    else await page.getByRole('button', { name: '继续编辑' }).click()
    await expect(editor).toBeFocused()
    await expect(editor).toHaveValue('未保存的合成更正')
  }
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '放弃修改', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(opener).toBeFocused()
})

for (const sourceAvailable of [true, false]) {
  test(`conflicting forgetting uses reviewed version with available source=${sourceAvailable}`, async ({
    page,
  }) => {
    const data = await fixture(page)
    await page.getByRole('button', { name: '遗忘', exact: true }).click()
    const confirm = page.getByRole('button', { name: '确认遗忘' })
    await expect(confirm).toBeEnabled()
    data.update(sourceAvailable)
    await confirm.click()
    await expect(page.getByRole('alert')).toContainText('版本冲突')
    await expect(confirm).toBeDisabled()
    await expect(page.getByRole('dialog')).toContainText('最新版本 2')
    await page.getByRole('button', { name: '已核对最新版本' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    expect(data.attempts.map((item) => item.version)).toEqual([1])
    await confirm.click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    expect(data.attempts.map((item) => item.version)).toEqual([1, 2])
    expect(data.attempts[0].key).toBeTruthy()
    expect(data.attempts[1].key).not.toBe(data.attempts[0].key)
    await expect(page.getByRole('combobox', { name: '记忆状态' })).toBeFocused()
    await expect(page.locator('.memory-card')).toHaveCount(0)
  })
}

for (const action of ['更正', '停止使用', '遗忘']) {
  test(`successful memory ${action} restores focus to a surviving control`, async ({
    page,
  }) => {
    await fixture(page)
    const opener = page.getByRole('button', { name: action, exact: true })
    await opener.click()
    if (action === '更正')
      await page.getByLabel('更正内容').fill('更正后的合成内容')
    await page
      .getByRole('button', {
        name:
          action === '更正'
            ? '保存更正'
            : action === '停止使用'
              ? '确认停止'
              : '确认遗忘',
      })
      .click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(
      action === '更正'
        ? opener
        : page.getByRole('combobox', { name: '记忆状态' }),
    ).toBeFocused()
  })
}
