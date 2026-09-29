import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { SettingsPage } from '../account-page'
import { SupportPage } from '../support-shell'

export const Route = createFileRoute('/me')({
  ssr: false,
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
  return (
    <SupportPage>
      <SettingsPage section={section} />
    </SupportPage>
  )
}
