import { createFileRoute } from '@tanstack/react-router'
import { MemoriesPage } from '../memories-page'

export const Route = createFileRoute('/_support/me_/memories')({
  head: () => ({ meta: [{ title: 'AI 记忆 · PsyEvoAgent' }] }),
  component: MemoriesPage,
})
