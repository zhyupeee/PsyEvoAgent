import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { ResourcesPage } from '../resources-page'
export const Route = createFileRoute('/_support/resources/')({
  validateSearch: z.object({
    tab: z.enum(['exercise', 'support']).default('exercise'),
  }),
  component: Page,
})
function Page() {
  const { tab } = Route.useSearch()
  return <ResourcesPage tab={tab} />
}
