import { z } from 'zod'

export const noteSchema = z.object({
  id: z.string(),
  version: z.number(),
  kind: z.enum(['free', 'linked_excerpt']),
  title: z.string(),
  body: z.string().nullable(),
  annotation: z.string(),
  occurred_at: z.string().nullable(),
  timezone: z.string().nullable(),
  tags: z.array(z.string()),
  status: z.enum(['draft', 'saved', 'needs_review', 'deleted']),
  source_refs: z.array(
    z.object({
      source_type: z.literal('message'),
      source_id: z.string(),
      source_version: z.number(),
    }),
  ),
  source_messages: z.array(
    z.object({
      id: z.string(),
      version: z.number(),
      role: z.string(),
      content: z.string(),
    }),
  ),
})
export const sleepSchema = z.object({
  id: z.string(),
  version: z.number(),
  entry_date: z.string(),
  bed_at: z.string().nullable(),
  wake_at: z.string().nullable(),
  timezone: z.string().nullable(),
  interruptions: z.number().nullable(),
  feeling: z.string(),
  note: z.string(),
  span_minutes: z.number().nullable(),
})
export const cardSchema = z.object({
  id: z.string().nullable(),
  version: z.number(),
  helpful_methods: z.string(),
  self_reminders: z.string(),
  contact_notes: z.string(),
  resource_refs: z.array(z.record(z.string(), z.string())),
  resource_status: z.string(),
  previous_content: z
    .object({
      version: z.number(),
      helpful_methods: z.string(),
      self_reminders: z.string(),
      contact_notes: z.string(),
    })
    .nullable(),
})
export type Note = z.infer<typeof noteSchema>
export type Sleep = z.infer<typeof sleepSchema>
export type Card = z.infer<typeof cardSchema>
export type RecordKind = 'note' | 'sleep_record' | 'support_card'
export const recordPaths = {
  note: '/notes',
  sleep_record: '/sleep-records',
  support_card: '/support-card',
}
