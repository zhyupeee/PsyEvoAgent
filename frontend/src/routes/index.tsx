import { createFileRoute } from '@tanstack/react-router'
import { AccountPage } from '../account-page'

export const Route = createFileRoute('/')({
  ssr: false,
  head: () => ({ meta: [{ title: '首页 · PsyEvoAgent' }] }),
  component: () => <AccountPage page="home" />,
})
