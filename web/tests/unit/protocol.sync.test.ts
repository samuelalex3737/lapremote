import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  agentPayloads,
  CLIENT_RULES,
  clientPayloads,
  encodeClientMessage,
  KEY_NAMES,
  parseAgentMessage,
} from '../../src/lib/protocol.ts'
import { zodDescriptor } from '../../src/lib/schemaDescriptor.ts'

const root = new URL('../../../', import.meta.url)
const protocolDoc = readFileSync(fileURLToPath(new URL('docs/PROTOCOL.md', root)), 'utf8')
const committedSchema = JSON.parse(
  readFileSync(fileURLToPath(new URL('shared/protocol.schema.json', root)), 'utf8'),
) as Record<string, Record<string, unknown>>

function docTypes(direction: string): string[] {
  const match = new RegExp('```text ' + direction + '\\r?\\n([\\s\\S]*?)```').exec(protocolDoc)
  if (match?.[1] === undefined) throw new Error(`PROTOCOL.md has no ${direction} block`)
  return match[1]
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}

describe('protocol.ts matches docs/PROTOCOL.md', () => {
  it('has every client -> agent type', () => {
    expect(Object.keys(clientPayloads).sort()).toEqual(docTypes('client-to-agent').sort())
    expect(Object.keys(CLIENT_RULES).sort()).toEqual(docTypes('client-to-agent').sort())
  })

  it('has every agent -> client type', () => {
    expect(Object.keys(agentPayloads).sort()).toEqual(docTypes('agent-to-client').sort())
  })
})

describe('protocol.ts matches protocol.py (shared/protocol.schema.json)', () => {
  const ours = zodDescriptor() as Record<string, Record<string, unknown>>

  it('uses the same protocol version', () => {
    expect(ours.version).toEqual(committedSchema.version)
  })

  for (const direction of ['clientToAgent', 'agentToClient'] as const) {
    const theirs = committedSchema[direction] ?? {}
    for (const type of Object.keys(theirs)) {
      it(`${direction} ${type} has the same fields, roles and enums`, () => {
        expect(ours[direction]?.[type]).toEqual(theirs[type])
      })
    }
  }

  it('includes media.artwork in both directions', () => {
    expect(ours.clientToAgent?.['media.artwork']).toBeDefined()
    expect(ours.agentToClient?.['media.artwork']).toBeDefined()
  })
})

describe('parseAgentMessage', () => {
  it('accepts a valid message', () => {
    const msg = parseAgentMessage(
      JSON.stringify({ v: 1, id: 's1', type: 'pong', payload: { t: 12.5 } }),
    )
    expect(msg).toEqual({ v: 1, id: 's1', type: 'pong', payload: { t: 12.5 } })
  })

  it('accepts media.artwork with a null image', () => {
    const msg = parseAgentMessage(
      JSON.stringify({
        v: 1,
        id: 's2',
        type: 'media.artwork',
        payload: { artworkId: 'ab12', artwork: null },
      }),
    )
    expect(msg?.type).toBe('media.artwork')
  })

  it.each([
    'not json',
    JSON.stringify({ v: 2, id: 's', type: 'pong', payload: { t: 1 } }),
    JSON.stringify({ v: 1, id: 's', type: 'shell', payload: {} }),
    JSON.stringify({ v: 1, id: 's', type: 'pong', payload: { t: 'x' } }),
    JSON.stringify({ v: 1, id: 's', type: 'pong', payload: { t: 1, extra: true } }),
  ])('rejects %s', (text) => {
    expect(parseAgentMessage(text)).toBeNull()
  })
})

describe('client payload rules', () => {
  it('encodes an envelope', () => {
    expect(JSON.parse(encodeClientMessage('ping', { t: 1 }, 'c1'))).toEqual({
      v: 1,
      id: 'c1',
      type: 'ping',
      payload: { t: 1 },
    })
  })

  it('allowlists key names', () => {
    expect(KEY_NAMES).toContain('f12')
    expect(clientPayloads['key.press'].safeParse({ key: 'F12' }).success).toBe(false)
    expect(clientPayloads['key.press'].safeParse({ key: 'f12', modifiers: ['ctrl'] }).success).toBe(
      true,
    )
  })

  it('needs exactly one of to or by for seek', () => {
    const seek = clientPayloads['media.seek']
    expect(seek.safeParse({ by: -120 }).success).toBe(true)
    expect(seek.safeParse({}).success).toBe(false)
    expect(seek.safeParse({ to: 1, by: 1 }).success).toBe(false)
  })

  it('rejects non-http shortcut urls', () => {
    const save = clientPayloads['shortcuts.save']
    expect(
      save.safeParse({
        shortcut: { id: 'x', name: 'X', kind: 'url', url: 'javascript:alert(1)' },
      }).success,
    ).toBe(false)
  })
})
