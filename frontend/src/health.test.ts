import { afterEach, expect, test, vi } from 'vitest'
import { checkHealth, parseHealth } from './health'

afterEach(() => vi.unstubAllGlobals())

test('strict health contract rejects malformed and unexpected fields', () => {
  expect(parseHealth({ status: 'ok', stage: 'S1-STEP02' }).status).toBe('ok')
  for (const value of [
    null,
    {},
    { status: 200 },
    { status: 'ok', stage: 'S1-STEP02', owner_id: 'other' },
  ]) {
    expect(() => parseHealth(value)).toThrow()
  }
})

test('HTTP errors do not become successful checks or expose response bodies', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(new Response('synthetic-private', { status: 500 })),
  )
  await expect(checkHealth(new AbortController().signal)).rejects.toThrow(
    'Health request failed',
  )
})
