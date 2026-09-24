import { createFileRoute } from '@tanstack/react-router'
import { AccountPage } from '../account-page'

export const Route = createFileRoute('/me')({
  ssr: false,
  head: () => ({ meta: [{ title: '我的账号 · PsyEvoAgent' }] }),
  component: () => <AccountPage page="me" />,
})
