import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { SettingsPage } from '../account-page'

export const Route = createFileRoute('/_support/me')({
  validateSearch: z.object({
    section: z
      .enum(['preferences', 'models', 'security', 'data'])
      .catch('preferences'),
  }),
  head: () => ({ meta: [{ title: '设置 · PsyEvoAgent' }] }),
  component: Page,
})

function Page() {
  const { section } = Route.useSearch()
  return <SettingsPage section={section} />
}
