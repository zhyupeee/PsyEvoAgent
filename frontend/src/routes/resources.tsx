import { createFileRoute, Outlet } from '@tanstack/react-router'
import { SupportPage } from '../support-shell'
export const Route = createFileRoute('/resources')({
  ssr: false,
  component: () => (
    <SupportPage>
      <Outlet />
    </SupportPage>
  ),
})
