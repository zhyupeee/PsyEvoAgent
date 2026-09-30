import { createFileRoute } from '@tanstack/react-router'
import { SupportCardPage } from '../records-page'
export const Route = createFileRoute('/_support/me_/support-card')({
  head: () => ({ meta: [{ title: '支持备忘卡 · PsyEvoAgent' }] }),
  component: SupportCardPage,
})
