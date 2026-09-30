import { createFileRoute } from '@tanstack/react-router'
import { RecordsPage } from '../records-page'
export const Route = createFileRoute('/_support/records/sleep')({
  head: () => ({ meta: [{ title: '睡眠记录 · PsyEvoAgent' }] }),
  component: () => <RecordsPage sleep />,
})
