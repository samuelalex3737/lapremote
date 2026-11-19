import { z } from 'zod'

/** Mirrors `HealthResponse` in agent/lapremote/server.py. */
export const healthSchema = z.object({
  app: z.literal('lapremote'),
  version: z.string().min(1),
  os: z.enum(['windows', 'macos', 'linux']),
})

export type Health = z.infer<typeof healthSchema>
export type HostOs = Health['os']

export class HealthError extends Error {
  override name = 'HealthError'
}

const OS_LABELS: Record<HostOs, string> = {
  windows: 'Windows',
  macos: 'macOS',
  linux: 'Linux',
}

export function describeOs(os: HostOs): string {
  return OS_LABELS[os]
}

export function parseHealth(data: unknown): Health {
  const result = healthSchema.safeParse(data)
  if (!result.success) {
    throw new HealthError("That doesn't look like a LapRemote agent.")
  }
  return result.data
}

export async function fetchHealth(
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<Health> {
  const init: RequestInit = { headers: { accept: 'application/json' } }
  if (signal !== undefined) {
    init.signal = signal
  }
  const response = await fetchImpl('/api/health', init)
  if (!response.ok) {
    throw new HealthError(`The agent answered with status ${String(response.status)}.`)
  }
  const body: unknown = await response.json()
  return parseHealth(body)
}
