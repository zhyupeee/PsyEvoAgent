import { createFileRoute } from '@tanstack/react-router'
import { ChatPage } from '../chat-page'
export const Route = createFileRoute('/chat/')({
  component: () => <ChatPage />,
})
