import { createFileRoute } from '@tanstack/react-router'
import { ChatPage } from '../chat-page'
import { z } from 'zod'
export const Route = createFileRoute('/_support/chat/$sessionId')({
  validateSearch: z.object({
    record: z.string().optional(),
    recordType: z.enum(['note', 'sleep_record', 'support_card']).optional(),
    recordVersion: z.number().int().positive().optional(),
  }),
  component: Page,
})
function Page() {
  const { sessionId } = Route.useParams()
  return <ChatPage sessionId={sessionId} />
}
