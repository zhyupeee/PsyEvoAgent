import { expect, test } from '@playwright/test'

test('feedback components support keyboard, drafts, cancellation and idempotent retry', async ({
  page,
}, testInfo) => {
  const session = {
    id: 'feedback-session',
    version: 1,
    title: '合成反馈会话',
    title_source: 'manual',
    title_revision: 1,
    title_generation_status: 'not_requested',
    status: 'active',
  }
  const run = {
    run_id: 'feedback-run',
    input_id: 'feedback-input',
    input_text: '合成输入',
    input_version: 1,
    version: 2,
    status: 'completed',
    is_current: true,
    generation: 1,
    last_event_id: '2',
    output: { text: '合成回答' },
  }
  const submissions: { key: string; body: unknown }[] = []
  await page.route('**/api/v1/**', async (route) => {
    const endpoint = new URL(route.request().url()).pathname
    let json: unknown
    if (endpoint.endsWith('/auth/session'))
      json = {
        user_id: 'feedback-user',
        email: 'feedback@example.com',
        csrf_token: 'synthetic',
      }
    else if (endpoint.endsWith('/me/preferences'))
      json = {
        version: 1,
        age_band: 'unknown',
        mode: 'listen',
        display_preferences: {
          font_size: 'normal',
          reduced_motion: true,
          hide_titles: false,
        },
      }
    else if (endpoint.endsWith('/sessions'))
      json = { items: [session], next_cursor: null, has_pending_titles: false }
    else if (endpoint.endsWith('/sessions/' + session.id)) json = session
    else if (endpoint.endsWith('/current-run')) json = run
    else if (endpoint.endsWith('/timeline'))
      json = { items: [run], next_cursor: null }
    else if (endpoint.endsWith('/feedback')) {
      submissions.push({
        key: route.request().headers()['idempotency-key'],
        body: route.request().postDataJSON(),
      })
      if (submissions.length === 1)
        return route.fulfill({ status: 503, json: { code: 'synthetic' } })
      json = { feedback_id: 'synthetic-receipt', status: 'saved' }
    } else json = { items: [], next_cursor: null }
    return route.fulfill({ json })
  })
  await page.goto('/chat/' + session.id)
  const panel = page.locator('.feedback-panel')
  const trigger = panel.getByRole('button', { name: '反馈或纠正 · 可跳过' })
  const comment = panel.getByLabel('补充说明（可选）')
  const helpfulness = panel.getByRole('combobox', { name: '这次回答' })
  await expect(trigger).toHaveAttribute('aria-expanded', 'false')
  await expect(panel.locator('details, summary')).toHaveCount(0)
  // Radix keeps aria-hidden native selects internally for form integration.
  await expect(panel.locator('select:not([aria-hidden="true"])')).toHaveCount(0)
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await trigger.focus()
    await page.keyboard.press('Enter')
    await expect(trigger).toHaveAttribute('aria-expanded', 'true')
    await helpfulness.focus()
    await page.keyboard.press('Space')
    await expect(page.getByRole('listbox')).toBeVisible()
    await expect(
      page.getByRole('option', { name: '不评价', exact: true }),
    ).toBeFocused()
    await page.keyboard.press('End')
    await expect(
      page.getByRole('option', { name: '不合适', exact: true }),
    ).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(helpfulness).toHaveText('不合适')
    await expect(helpfulness).toBeFocused()
    await panel.getByRole('combobox', { name: '反馈类型' }).click()
    await page.getByRole('option', { name: '这里误解了我' }).click()
    await comment.fill('保留草稿')
    await trigger.click()
    await expect(comment).toBeHidden()
    await trigger.press('Space')
    await expect(comment).toHaveValue('保留草稿')
    await expect(helpfulness).toHaveText('不合适')
    await panel.getByRole('button', { name: '取消反馈' }).click()
    await expect(trigger).toHaveAttribute('aria-expanded', 'false')
    await expect(trigger).toBeFocused()
    await trigger.press('Enter')
    await expect(comment).toHaveValue('')
    await expect(helpfulness).toHaveText('不评价')
    await expect(panel.getByRole('combobox', { name: '反馈类型' })).toHaveText(
      '一般反馈',
    )
    expect(submissions).toHaveLength(0)
    await panel.screenshot({
      path: testInfo.outputPath(`feedback-${width}.png`),
    })
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true)
    await trigger.click()
  }
  await trigger.click()
  const submit = panel.getByRole('button', { name: '提交反馈' })
  await submit.click()
  await expect(panel.getByRole('alert')).toContainText('反馈未确认')
  await submit.click()
  await expect(panel.getByRole('status')).toContainText('synthetic-receipt')
  expect(submissions).toHaveLength(2)
  expect(submissions[0]).toEqual(submissions[1])
  expect(submissions[0].key).toBeTruthy()
  expect(submissions[0].body).toEqual({
    run_id: run.run_id,
    helpfulness: 'not_rated',
    category: 'general',
    comment: '',
  })
})
