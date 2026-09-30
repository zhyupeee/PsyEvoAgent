import { createFileRoute } from '@tanstack/react-router'
import { RecordsPage } from '../records-page'
export const Route = createFileRoute('/_support/records/')({
  head: () => ({ meta: [{ title: '我的记录 · PsyEvoAgent' }] }),
  component: RecordsPage,
})
