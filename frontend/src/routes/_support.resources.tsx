import { createFileRoute, Outlet } from '@tanstack/react-router'
export const Route = createFileRoute('/_support/resources')({
  component: Outlet,
})
