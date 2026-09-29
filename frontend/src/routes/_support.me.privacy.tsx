import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_support/me/privacy')({
  beforeLoad: () => {
    throw redirect({
      to: '/me',
      search: { section: 'preferences' },
      replace: true,
    })
  },
})
