import { expect, test } from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

test('two synthetic live turns retain conversation context', async ({
  page,
  context,
}) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort(),
  )
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill('step08-live@example.com')
  await page
    .getByLabel('密码', { exact: true })
    .fill('synthetic-browser-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/chat')
  await page.getByRole('button', { name: '开始一次对话' }).click()
  // Manual title before the first turn prevents a third paid title call.
  await page.getByText('管理此对话', { exact: true }).click()
  await page.getByLabel('对话标题').fill('同会话合成多轮验证')
  await page.getByRole('button', { name: '保存标题' }).click()
  await expect(page.locator('.chat-title')).toHaveText('同会话合成多轮验证')
  await page.getByText('管理此对话', { exact: true }).click()
  const runs: string[] = []
  for (const text of [
    '这是合成对话，没有真实个人信息。我给虚构纸船起的名字是“青苔月舟”。请只用一句话复述这个名字，不需要建议。',
    '我刚才给那艘虚构纸船起的名字是什么？请只回答名字，不需要建议。',
  ]) {
    await page.getByLabel('想说的事').fill(text)
    const started = page.waitForResponse(
      (r) =>
        /\/runs\/[^/]+\/start$/.test(r.url()) &&
        r.request().method() === 'POST',
    )
    await page.getByRole('button', { name: '发送', exact: true }).click()
    runs.push((await (await started).json()).run_id)
    // Fail promptly on a persisted terminal error; never retry a paid call.
    await expect
      .poll(
        async () =>
          page.evaluate(async (id) => {
            const result = await fetch(`/api/v1/runs/${id}`)
            return (await result.json()).status as string
          }, runs.at(-1)!),
        { timeout: 125000 },
      )
      .toMatch(/completed|failed|cancelled|interrupted/)
    await expect(page.getByRole('status')).toContainText('已完成')
    await expect(page.locator('.assistant-message')).toHaveCount(runs.length, {
      timeout: 125000,
    })
    await expect(page.getByRole('status')).toContainText('已完成')
    await expect(page.locator('.assistant-message').last()).toContainText(
      '青苔月舟',
    )
  }
  await page.reload()
  await expect(page.locator('.assistant-message')).toHaveCount(2)
  await expect(page.locator('.user-message')).toHaveCount(2)
  const facts = await page.evaluate(async (ids) => {
    const results = await Promise.all(
      ids.map(async (id) => (await fetch(`/api/v1/runs/${id}`)).json()),
    )
    return results.map((run) => ({
      run_id: run.run_id,
      status: run.status,
      budget: run.budget,
      usage: run.budget_used,
    }))
  }, runs)
  for (const fact of facts) {
    expect(fact.status).toBe('completed')
    expect(fact.budget.max_tokens).toBe(32768)
    expect(fact.usage.calls).toBe(1)
  }
  const directory = process.env.PSYEVO_STEP08_ARTIFACTS!
  await page.screenshot({
    path: path.join(directory, 'multiturn-live.png'),
    fullPage: true,
  })
  await fs.writeFile(
    path.join(directory, 'multiturn-live.json'),
    JSON.stringify(
      {
        synthetic: true,
        context_recalled: true,
        persisted_after_reload: true,
        runs: facts,
      },
      null,
      2,
    ),
  )
})
