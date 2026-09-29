import { expect, test } from '@playwright/test'
import path from 'node:path'

test('account model settings persist, hide keys, switch modes and revoke', async ({
  page,
  context,
}) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
  await page.goto('/login')
  await page
    .getByLabel('邮箱', { exact: true })
    .fill('model-settings@example.com')
  await page
    .getByLabel('密码', { exact: true })
    .fill('synthetic-model-password')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/chat')
  await page.goto('/me?section=models')
  await expect(
    page.getByRole('heading', { name: '模型配置', exact: true }),
  ).toBeVisible()
  await page.getByLabel('使用自己的 API', { exact: true }).check()
  await page
    .getByLabel('API Base URL', { exact: true })
    .fill('https://example.com/v1')
  await page
    .getByLabel('模型名称', { exact: true })
    .fill('synthetic-browser-model')
  await page
    .getByLabel('API Key', { exact: true })
    .fill('synthetic-browser-key')
  await page.getByRole('button', { name: '保存模型配置', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已保存')
  await expect(page.getByLabel('API Key', { exact: true })).toHaveValue('')
  await page.reload()
  await expect(page.getByLabel('使用自己的 API', { exact: true })).toBeChecked()
  await expect(page.getByLabel('模型名称', { exact: true })).toHaveValue(
    'synthetic-browser-model',
  )
  await expect(page.getByLabel('API Key', { exact: true })).toHaveAttribute(
    'placeholder',
    /已配置/,
  )
  const state = await page.evaluate(async () => ({
    settings: await (await fetch('/api/v1/me/model-settings')).text(),
    storage: JSON.stringify(localStorage),
  }))
  expect(JSON.stringify(state)).not.toContain('synthetic-browser-key')
  await page.getByLabel('官方提供', { exact: true }).check()
  await page.getByRole('button', { name: '保存模型配置', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已保存')
  await page.reload()
  await expect(page.getByLabel('官方提供', { exact: true })).toBeChecked()
  await page.getByLabel('使用自己的 API', { exact: true }).check()
  await page.getByRole('button', { name: '保存模型配置', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('已保存')
  await page
    .getByRole('button', { name: '测试已保存配置', exact: true })
    .click()
  await expect(page.getByRole('status')).toContainText('尚未启用')
  await page.setViewportSize({ width: 390, height: 844 })
  const directory = process.env.PSYEVO_MODEL_SETTINGS_ARTIFACTS
  if (directory)
    await page.screenshot({
      path: path.join(directory, 'model-settings-mobile.png'),
      fullPage: true,
    })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page.getByRole('button', { name: '删除个人配置', exact: true }).click()
  await page.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('个人配置已删除')
  await page.reload()
  await expect(page.getByLabel('官方提供', { exact: true })).toBeChecked()
  await expect(
    page.getByRole('button', { name: '删除个人配置', exact: true }),
  ).toHaveCount(0)
})
