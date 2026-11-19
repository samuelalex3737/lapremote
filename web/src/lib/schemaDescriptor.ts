/**
 * Normalises a JSON Schema into the same structure protocol.py writes to
 * shared/protocol.schema.json, so the zod mirror can be compared field by field.
 * Mirrors `_normalise` in agent/lapremote/protocol.py.
 */
import { z } from 'zod'
import { agentPayloads, CLIENT_RULES, clientPayloads, PROTOCOL_VERSION } from './protocol.ts'

type JsonSchema = Record<string, unknown>
export type Normalised = Record<string, unknown>

const NULL_TYPE = JSON.stringify({ type: 'null' })

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0,
    )
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${stableStringify(v)}`).join(',')}}`
  }
  return JSON.stringify(value)
}

function resolve(node: JsonSchema, defs: Record<string, JsonSchema>): JsonSchema {
  let current = node
  while (typeof current.$ref === 'string') {
    const name = current.$ref.split('/').pop() ?? ''
    const next = defs[name]
    if (next === undefined) throw new Error(`unresolved $ref ${current.$ref}`)
    current = next
  }
  return current
}

function sortValues(values: unknown[]): unknown[] {
  return [...values].sort((a, b) => {
    const x = String(a)
    const y = String(b)
    return x < y ? -1 : x > y ? 1 : 0
  })
}

export function normalise(input: JsonSchema, defs: Record<string, JsonSchema>): Normalised {
  const node = resolve(input, defs)
  if (Array.isArray(node.type)) {
    // zod writes nullable primitives as {"type": ["string", "null"]}; pydantic uses anyOf.
    const types = node.type as unknown[]
    return normalise({ anyOf: types.map((t) => ({ ...node, type: t })) }, defs)
  }
  const variants = (node.anyOf ?? node.oneOf) as JsonSchema[] | undefined
  if (variants !== undefined) {
    const members = variants.map((v) => normalise(v, defs))
    const nullable = members.some((m) => JSON.stringify(m) === NULL_TYPE)
    const rest = members.filter((m) => JSON.stringify(m) !== NULL_TYPE)
    const base: Normalised =
      rest.length === 1 && rest[0] !== undefined
        ? rest[0]
        : {
            union: [...rest].sort((a, b) => {
              const x = stableStringify(a)
              const y = stableStringify(b)
              return x < y ? -1 : x > y ? 1 : 0
            }),
          }
    return nullable ? { nullable: base } : base
  }
  if ('const' in node) return { enum: [node.const] }
  if (Array.isArray(node.enum)) return { enum: sortValues(node.enum) }
  const kind = node.type
  if (kind === 'object') {
    const props = node.properties as Record<string, JsonSchema> | undefined
    if (props === undefined) return { type: 'record' }
    const required = new Set((node.required as string[] | undefined) ?? [])
    const out: Record<string, Normalised> = {}
    for (const name of Object.keys(props).sort()) {
      const sub = props[name]
      if (sub === undefined) continue
      out[name] = { required: required.has(name), schema: normalise(sub, defs) }
    }
    return { object: out }
  }
  if (kind === 'array') {
    return { array: normalise((node.items as JsonSchema | undefined) ?? {}, defs) }
  }
  if (
    kind === 'string' ||
    kind === 'integer' ||
    kind === 'number' ||
    kind === 'boolean' ||
    kind === 'null'
  ) {
    return { type: kind }
  }
  return { type: 'unknown' }
}

function describe(schema: z.ZodType): Normalised {
  const json = z.toJSONSchema(schema, { io: 'input', unrepresentable: 'any' }) as JsonSchema
  const defs = (json.$defs ?? {}) as Record<string, JsonSchema>
  return normalise(json, defs)
}

/** The full descriptor, in the same shape as shared/protocol.schema.json. */
export function zodDescriptor(): Record<string, unknown> {
  const clientToAgent: Record<string, unknown> = {}
  for (const name of Object.keys(clientPayloads).sort()) {
    const type = name as keyof typeof clientPayloads
    clientToAgent[name] = {
      payload: describe(clientPayloads[type]),
      reply: CLIENT_RULES[type].reply,
      role: CLIENT_RULES[type].role,
    }
  }
  const agentToClient: Record<string, unknown> = {}
  for (const name of Object.keys(agentPayloads).sort()) {
    agentToClient[name] = { payload: describe(agentPayloads[name as keyof typeof agentPayloads]) }
  }
  return { agentToClient, clientToAgent, version: PROTOCOL_VERSION }
}
