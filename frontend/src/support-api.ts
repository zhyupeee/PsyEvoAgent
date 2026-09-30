import { z } from 'zod'
import { request } from './account-api'

export const preferencesSchema = z.object({
  version: z.number(),
  age_band: z.enum(['adult', 'minor', 'unknown']),
  mode: z.enum(['listen', 'explore']),
  display_preferences: z.object({
    font_size: z.enum(['normal', 'large']).default('normal'),
    reduced_motion: z.boolean().default(true),
    hide_titles: z.boolean().default(false),
  }),
})
export const preferencesQuery = {
  queryKey: ['preferences'],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    request('/me/preferences', preferencesSchema, { signal }),
}
export const sessionSchema = z.object({
  id: z.string(),
  version: z.number(),
  title: z.string(),
  title_source: z.enum(['default', 'auto', 'manual']),
  title_revision: z.number(),
  title_generation_status: z.enum([
    'not_requested',
    'queued',
    'running',
    'succeeded',
    'failed',
    'cancelled',
  ]),
  status: z.enum(['active', 'archived', 'deleted']),
})
export const titlePending = (session: z.infer<typeof sessionSchema>) =>
  ['queued', 'running'].includes(session.title_generation_status)
export const runSchema = z.object({
  run_id: z.string(),
  version: z.number(),
  status: z.enum([
    'draft',
    'queued',
    'running',
    'completed',
    'cancelled',
    'failed',
    'interrupted',
  ]),
  generation: z.number().default(0),
  last_event_id: z.string().default('0'),
  stop_reason: z.string().nullable().optional(),
  output: z
    .object({
      text: z.string(),
      id: z.string().optional(),
      version: z.number().optional(),
    })
    .nullable()
    .optional(),
  input_text: z.string().nullable().optional(),
  input_id: z.string().nullable().optional(),
  input_version: z.number().nullable().optional(),
  is_current: z.boolean().optional(),
  created_at: z.string().optional(),
  parent_run_id: z.string().nullable().optional(),
})
export type Run = z.infer<typeof runSchema>
export const terminal = (run: Run) =>
  ['completed', 'cancelled', 'failed', 'interrupted'].includes(run.status)
export const exerciseSchema = z.object({
  title: z.string(),
  version: z.string(),
  review_status: z.string(),
  available: z.boolean(),
  steps: z.array(z.string()),
})
