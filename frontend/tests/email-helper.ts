import { expect, type Page } from '@playwright/test'
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'

export async function mailCode(email: string): Promise<string> {
  const directory = process.env.PSYEVO_TEST_MAIL_DIR
  if (!directory) throw new Error('Isolated synthetic outbox is required')
  let code = ''
  await expect
    .poll(async () => {
      const messages = await Promise.all(
        (await readdir(directory)).map(
          async (name) =>
            JSON.parse(await readFile(path.join(directory, name), 'utf8')) as {
              email: string
              body: string
            },
        ),
      )
      const message = messages.find(
        (item) => item.email === email && /\b[0-9]{6}\b/.test(item.body),
      )
      code = message?.body.match(/\b[0-9]{6}\b/)?.[0] ?? ''
      return code
    })
    .not.toBe('')
  return code
}

export async function register(page: Page, email: string) {
  await page.goto('/register')
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page.getByRole('button', { name: '发送验证码' }).click()
  await expect(page.getByRole('status')).toContainText('验证码已发送')
  await page
    .getByLabel('邮箱验证码', { exact: true })
    .fill(await mailCode(email))
  await page.getByLabel('密码', { exact: true }).fill('12345678')
  await page.getByLabel('确认新密码').fill('12345678')
  await page.getByRole('button', { name: '注册并进入' }).click()
  await expect(page).toHaveURL('/')
}
