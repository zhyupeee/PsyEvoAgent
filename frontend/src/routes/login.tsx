import { createFileRoute } from '@tanstack/react-router'
import { AccountPage } from '../account-page'

export const Route = createFileRoute('/login')({
  ssr: false,
  head: () => ({ meta: [{ title: '登录 · PsyEvoAgent' }] }),
  component: () => <AccountPage page="login" />,
})
