import { createFileRoute } from '@tanstack/react-router'
import { z } from 'zod'
import { ExercisePage } from '../resources-page'
export const Route = createFileRoute('/resources/exercises/$exerciseId')({
  validateSearch: z.object({ from: z.string().uuid().optional() }),
  component: Page,
})
function Page() {
  const { exerciseId } = Route.useParams()
  const { from } = Route.useSearch()
  return <ExercisePage key={exerciseId} exerciseId={exerciseId} from={from} />
}
