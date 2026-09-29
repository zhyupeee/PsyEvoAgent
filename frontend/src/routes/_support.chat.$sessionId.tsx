import { createFileRoute } from '@tanstack/react-router'
import { ChatPage } from '../chat-page'
export const Route = createFileRoute('/_support/chat/$sessionId')({
  component: Page,
})
function Page() {
  const { sessionId } = Route.useParams()
  return <ChatPage sessionId={sessionId} />
}
