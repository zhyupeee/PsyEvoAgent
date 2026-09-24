import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/me/privacy')({
  beforeLoad: () => {
    throw redirect({ to: '/me', replace: true })
  },
})
