import { describe, expect, it } from 'vitest'
import { mergeTurns } from './chat-timeline'
import { type Run } from './support-api'

const turn = (id: string, overrides: Partial<Run> = {}): Run => ({
  run_id: id,
  input_id: id,
  version: 2,
  status: 'completed',
  generation: 1,
  last_event_id: '1',
  is_current: true,
  created_at: `2026-09-28T00:00:0${id}Z`,
  ...overrides,
})

describe('conversation snapshot merging', () => {
  it('retains earlier turns and ignores an older version of the current run', () => {
    const latest = turn('2', { version: 4, output: { text: '发布回答' } })
    expect(mergeTurns([[turn('1'), latest], [turn('1')]], turn('2'))).toEqual([
      turn('1'),
      latest,
    ])
  })
  it('removes superseded branches including a chain across pages', () => {
    const draft = turn('3', { status: 'draft', parent_run_id: '2' })
    expect(
      mergeTurns([[turn('1')], [turn('2', { parent_run_id: '1' })]], draft),
    ).toEqual([draft])
  })
  it('does not turn an empty send draft into a displayed message', () => {
    expect(mergeTurns([[turn('1')]], turn('2', { input_id: null }))).toEqual([
      turn('1'),
    ])
  })
})
