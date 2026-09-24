import { createFileRoute } from '@tanstack/react-router'
import { AccountPage } from '../account-page'

export const Route = createFileRoute('/register')({
  ssr: false,
  head: () => ({ meta: [{ title: '注册 · PsyEvoAgent' }] }),
  component: () => <AccountPage page="register" />,
})
