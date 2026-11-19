import { describe, expect, it } from 'vitest'
import { describeOs, fetchHealth, HealthError, parseHealth } from '../../src/lib/health.ts'

const valid = { app: 'lapremote', version: '0.1.0', os: 'windows' }

function fakeFetch(status: number, body: unknown): typeof fetch {
  return (input) => {
    expect(input).toBe('/api/health')
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    )
  }
}

describe('parseHealth', () => {
  it('accepts a valid agent response', () => {
    expect(parseHealth(valid)).toEqual(valid)
  })

  it('rejects a different app', () => {
    expect(() => parseHealth({ ...valid, app: 'other' })).toThrow(HealthError)
  })

  it('rejects an unknown OS', () => {
    expect(() => parseHealth({ ...valid, os: 'freebsd' })).toThrow(HealthError)
  })

  it('rejects an empty version', () => {
    expect(() => parseHealth({ ...valid, version: '' })).toThrow(HealthError)
  })

  it('rejects non-objects', () => {
    expect(() => parseHealth('ok')).toThrow(HealthError)
    expect(() => parseHealth(null)).toThrow(HealthError)
  })
})

describe('fetchHealth', () => {
  it('returns parsed health on 200', async () => {
    await expect(fetchHealth(undefined, fakeFetch(200, valid))).resolves.toEqual(valid)
  })

  it('throws a friendly error on non-200', async () => {
    await expect(fetchHealth(undefined, fakeFetch(502, {}))).rejects.toThrow(
      'The agent answered with status 502.',
    )
  })

  it('throws when the body is not an agent response', async () => {
    await expect(fetchHealth(undefined, fakeFetch(200, { hello: 1 }))).rejects.toThrow(
      HealthError,
    )
  })

  it('passes the abort signal through', async () => {
    const controller = new AbortController()
    let seen: AbortSignal | null | undefined
    const spy: typeof fetch = (_input, init) => {
      seen = init?.signal
      return Promise.resolve(new Response(JSON.stringify(valid), { status: 200 }))
    }
    await fetchHealth(controller.signal, spy)
    expect(seen).toBe(controller.signal)
  })
})

describe('describeOs', () => {
  it('uses friendly names', () => {
    expect(describeOs('windows')).toBe('Windows')
    expect(describeOs('macos')).toBe('macOS')
    expect(describeOs('linux')).toBe('Linux')
  })
})
