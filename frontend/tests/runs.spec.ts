import { expect, test } from '@playwright/test'

test('real gateway: draft/grant/start, EventSource disconnect/replay, snapshot and revoke', async ({
  page,
  context,
}) => {
  await context.route('**/*', (route) =>
    new URL(route.request().url()).hostname === '127.0.0.1'
      ? route.continue()
      : route.abort('blockedbyclient'),
  )
  await page.goto('/health')
  // A test-only browser consumer exercises the existing gateway; no STEP06 UI.
  const result = await page.evaluate(async () => {
    const login = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: 'step05-browser@example.com',
        password: 'synthetic-browser-password',
      }),
    })
    if (!login.ok) throw new Error(`login ${login.status}`)
    const identity: { csrf_token: string } = await login.json()
    const write = async (
      path: string,
      body: unknown,
      key = crypto.randomUUID(),
      method = 'POST',
    ) => {
      const response = await fetch('/api/v1' + path, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': identity.csrf_token,
          'Idempotency-Key': key,
        },
        body: JSON.stringify(body),
      })
      if (!response.ok) throw new Error(`${path}: ${response.status}`)
      return response.status === 204 ? null : response.json()
    }
    const session: { id: string } = await write('/sessions', {})
    const draft: { run_id: string } = await write('/run-drafts', {
      context_type: 'conversation',
      session_id: session.id,
      expected_session_version: 1,
    })
    const grant: { id: string } = await write('/context-grants', {
      run_id: draft.run_id,
      source_type: 'conversation',
      source_id: session.id,
      source_version: 1,
      purpose: 'current_run',
    })
    const path = '/runs/' + draft.run_id
    const key = crypto.randomUUID()
    const body = {
      input: { message: '合成网关输入，只想倾听' },
      expected_version: 1,
      expected_session_version: 1,
      client_message_id: crypto.randomUUID(),
      grant_ids: [grant.id],
    }
    const first: { run_id: string } = await write(path + '/start', body, key)
    const second: { run_id: string } = await write(path + '/start', body, key)
    type Envelope = {
      schema_version: string
      run_id: string
      event_id: string
      type: string
      payload: { text?: string }
    }
    const stream = (cursor: string, stopAt: string) =>
      new Promise<Envelope[]>((resolve, reject) => {
        const source = new EventSource(
          '/api/v1' + path + '/events?after_event_id=' + cursor,
        )
        const items: Envelope[] = []
        const timer = setTimeout(() => {
          source.close()
          reject(new Error('stream timeout'))
        }, 15000)
        const close = () => {
          clearTimeout(timer)
          source.close()
        }
        for (const type of [
          'run.started',
          'message.delta',
          'run.completed',
          'run.failed',
          'run.cancelled',
        ]) {
          source.addEventListener(type, (raw) => {
            const event = raw as MessageEvent<string>
            const value = JSON.parse(event.data) as Envelope
            if (
              value.event_id !== event.lastEventId ||
              value.schema_version !== 'public-run-events/1'
            ) {
              close()
              reject(new Error('invalid envelope'))
              return
            }
            items.push(value)
            if (type === stopAt) {
              close()
              resolve(items)
            }
          })
        }
        source.onerror = () => {
          close()
          reject(new Error('stream handshake/lifecycle failure'))
        }
      })
    const startedAt = performance.now()
    const disconnected = await stream('0', 'run.started')
    const firstEventMs = performance.now() - startedAt
    const cursor = disconnected.at(-1)?.event_id ?? '0'
    const resumed = await stream(cursor, 'run.completed')
    const replay = await stream(cursor, 'run.completed')
    const deduplicated = new Map(
      [...disconnected, ...resumed, ...replay].map((e) => [e.event_id, e]),
    )
    const output = [...deduplicated.values()]
      .filter((e) => e.type === 'message.delta')
      .map((e) => e.payload.text)
      .join('')
    const snapshot = (await (await fetch('/api/v1' + path)).json()) as {
      status: string
      output: { text: string }
      version: number
    }
    const cancel = (await write(path + '/cancel', { expected_version: 1 })) as {
      status: string
    }
    await write('/checks' + path + '/expire-cursor', {})
    const expired = await fetch('/api/v1' + path + '/events?after_event_id=1')
    const recovered = (await (await fetch('/api/v1' + path)).json()) as {
      output: { text: string }
    }
    await write(
      '/context-grants/' + grant.id,
      { expected_version: 1 },
      crypto.randomUUID(),
      'DELETE',
    )
    const revoked = await fetch('/api/v1' + path + '/events?after_event_id=1')
    const revokedText = await revoked.text()
    return {
      sameRun: first.run_id === second.run_id,
      types: [...deduplicated.values()].map((e) => e.type),
      output,
      snapshot,
      cancel,
      expired: expired.status,
      recovered,
      revoked: revoked.status,
      revokedText,
      firstEventMs,
    }
  })
  expect(result.sameRun).toBe(true)
  expect(result.types).toEqual([
    'run.started',
    'message.delta',
    'run.completed',
  ])
  expect(result.output).toBe(result.snapshot.output.text)
  expect(result.cancel.status).toBe('completed')
  expect(result.expired).toBe(410)
  expect(result.recovered.output.text).toBe(result.output)
  expect(result.revoked).toBe(404)
  expect(result.revokedText).not.toContain(result.output)
  expect(result.firstEventMs).toBeLessThan(5000)
})
