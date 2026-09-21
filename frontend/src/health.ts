export type Health = { status: 'ok'; stage: 'S1-STEP02' }

export function parseHealth(value: unknown): Health {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('status' in value) ||
    value.status !== 'ok' ||
    !('stage' in value) ||
    value.stage !== 'S1-STEP02' ||
    Object.keys(value).length !== 2
  )
    throw new Error('Invalid health response')
  return { status: 'ok', stage: 'S1-STEP02' }
}

export async function checkHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch('/api/v1/health', { signal, cache: 'no-store' })
  if (!response.ok) throw new Error('Health request failed')
  return parseHealth(await response.json())
}
