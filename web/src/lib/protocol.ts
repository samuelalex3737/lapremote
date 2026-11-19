/**
 * LapRemote wire protocol - zod mirror of agent/lapremote/protocol.py.
 *
 * protocol.py is the source of truth. tests/unit/protocol.sync.test.ts fails if
 * this file drifts from docs/PROTOCOL.md or shared/protocol.schema.json.
 */
import { z } from 'zod'

export const PROTOCOL_VERSION = 1

const obj = z.strictObject

// ---------------------------------------------------------------- building blocks

export const roleSchema = z.enum(['owner', 'guest'])
export const osSchema = z.enum(['windows', 'macos', 'linux'])
export const buttonSchema = z.enum(['left', 'right', 'middle'])
export const modifierSchema = z.enum(['ctrl', 'alt', 'shift', 'meta'])
export const powerActionSchema = z.enum(['lock', 'sleep', 'shutdown', 'restart'])
export type PowerActionName = z.infer<typeof powerActionSchema>
export const timerModeSchema = z.enum(['minutes', 'end_of_media'])
export const timerThenSchema = z.enum(['pause', 'pause_lock', 'pause_sleep'])
export const mediaStatusSchema = z.enum(['playing', 'paused', 'stopped'])
export const contextCategorySchema = z.enum([
  'browser',
  'music',
  'video',
  'presentation',
  'desktop',
  'other',
])
export const siteSchema = z.enum(['youtube', 'netflix', 'prime', 'spotify_web', 'generic'])
export const toastLevelSchema = z.enum(['info', 'success', 'warn', 'error'])
export const authFailReasonSchema = z.enum([
  'invalid_code',
  'expired_code',
  'bad_token',
  'rate_limited',
])

const idStr = z
  .string()
  .min(1)
  .max(64)
  .regex(/^[A-Za-z0-9_.-]+$/)
const coord = z.number().min(-10_000).max(10_000)
const unit = z.number().min(0).max(1)
const level = z.int().min(0).max(100)
const monitorIndex = z.int().min(0).max(16)
const timestamp = z.number().min(0)

const letters = 'abcdefghijklmnopqrstuvwxyz'.split('')
const digits = '0123456789'.split('')
const fKeys = Array.from({ length: 24 }, (_, i) => `f${String(i + 1)}`)

export const KEY_NAMES = [
  ...letters,
  ...digits,
  ...fKeys,
  'enter',
  'esc',
  'tab',
  'backspace',
  'delete',
  'insert',
  'space',
  'up',
  'down',
  'left',
  'right',
  'home',
  'end',
  'pageup',
  'pagedown',
  'capslock',
  'printscreen',
  'menu',
  '`',
  '-',
  '=',
  '[',
  ']',
  '\\',
  ';',
  "'",
  ',',
  '.',
  '/',
  'media_play_pause',
  'media_next',
  'media_prev',
  'volume_up',
  'volume_down',
  'volume_mute',
] as const
export const keyNameSchema = z.enum(KEY_NAMES)
export type KeyName = z.infer<typeof keyNameSchema>
export type Modifier = z.infer<typeof modifierSchema>

export const emptySchema = obj({})

// ---------------------------------------------------------------- shared data models

export const shortcutSchema = obj({
  id: idStr,
  name: z.string().min(1).max(40),
  kind: z.enum(['url', 'app']),
  url: z.string().max(2048).nullish(),
  app: z.string().max(1024).nullish(),
  icon: z.string().max(40).nullish(),
}).superRefine((s, ctx) => {
  if (s.kind === 'url') {
    if (s.url == null || !/^https?:\/\//.test(s.url)) {
      ctx.addIssue({ code: 'custom', message: 'url shortcuts need an http or https url' })
    }
    if (s.app != null) ctx.addIssue({ code: 'custom', message: 'url shortcuts cannot have an app' })
  } else {
    if (!s.app) ctx.addIssue({ code: 'custom', message: 'app shortcuts need an app' })
    if (s.url != null) ctx.addIssue({ code: 'custom', message: 'app shortcuts cannot have a url' })
  }
})
export type Shortcut = z.infer<typeof shortcutSchema>

export const sceneStepSchema = z.discriminatedUnion('type', [
  obj({ type: z.literal('volume.set'), level }),
  obj({ type: z.literal('brightness.set'), level }),
  obj({ type: z.literal('launch.open'), shortcutId: idStr }),
  obj({ type: z.literal('media.play') }),
  obj({ type: z.literal('media.pause') }),
  obj({ type: z.literal('wait'), ms: z.int().min(0).max(600_000) }),
])
export type SceneStep = z.infer<typeof sceneStepSchema>

export const sceneSchema = obj({
  id: idStr,
  name: z.string().min(1).max(40),
  steps: z.array(sceneStepSchema).min(1).max(50),
})
export type Scene = z.infer<typeof sceneSchema>

export const featureStatusSchema = obj({
  available: z.boolean(),
  reason: z.string().nullish(),
})
export const featuresSchema = obj({
  input: featureStatusSchema,
  media: featureStatusSchema,
  volume: featureStatusSchema,
  brightness: featureStatusSchema,
  preview: featureStatusSchema,
  context: featureStatusSchema,
  power: featureStatusSchema,
  launcher: featureStatusSchema,
  scenes: featureStatusSchema,
  timer: featureStatusSchema,
  ai: featureStatusSchema,
  secureContext: z.boolean(),
})
export type Features = z.infer<typeof featuresSchema>
export type FeatureName = Exclude<keyof Features, 'secureContext'>

export const mediaSessionSchema = obj({
  id: z.string(),
  appId: z.string(),
  appName: z.string(),
  title: z.string(),
  artist: z.string(),
  album: z.string(),
  artworkId: z.string().nullable(),
  artwork: z.string().nullable(),
  status: mediaStatusSchema,
  position: z.number().nullable(),
  duration: z.number().nullable(),
  rate: z.number(),
  canSeek: z.boolean(),
  canNext: z.boolean(),
  canPrev: z.boolean(),
  updatedAt: timestamp,
})
export type MediaSession = z.infer<typeof mediaSessionSchema>

export const monitorInfoSchema = obj({
  index: monitorIndex,
  left: z.int(),
  top: z.int(),
  width: z.int().positive(),
  height: z.int().positive(),
  primary: z.boolean(),
})
export type MonitorInfo = z.infer<typeof monitorInfoSchema>

export const deviceInfoSchema = obj({
  deviceId: z.string(),
  name: z.string(),
  platform: z.string(),
  role: roleSchema,
  pairedAt: timestamp,
  lastSeenAt: timestamp.nullable(),
  online: z.boolean(),
})
export type DeviceInfo = z.infer<typeof deviceInfoSchema>

export const AI_ACTION_TYPES = [
  'media.toggle',
  'media.play',
  'media.pause',
  'media.next',
  'media.prev',
  'media.seek',
  'media.select',
  'volume.set',
  'volume.step',
  'volume.mute',
  'brightness.set',
  'power.action',
  'launch.open',
  'scene.run',
  'timer.set',
  'timer.cancel',
  'key.press',
  'key.text',
  'wait',
] as const

export const aiActionSchema = obj({
  type: z.enum(AI_ACTION_TYPES),
  payload: z.record(z.string(), z.unknown()).optional(),
})
export type AiAction = z.infer<typeof aiActionSchema>

export const aiStepResultSchema = obj({
  type: z.string(),
  ok: z.boolean(),
  error: z.string().nullish(),
})

// ---------------------------------------------------------------- client -> agent payloads

const mediaTarget = obj({ sessionId: z.string().nullish() })
const inputButton = obj({ button: buttonSchema })

export const clientPayloads = {
  'auth.pair': obj({
    code: z.string().regex(/^\d{6}$/),
    deviceName: z.string().min(1).max(64),
    platform: z.string().min(1).max(32),
  }),
  'auth.resume': obj({
    deviceId: z.string().min(1).max(64),
    token: z.string().min(1).max(128),
  }),
  'input.move': obj({ dx: coord, dy: coord }),
  'input.click': inputButton,
  'input.down': inputButton,
  'input.up': inputButton,
  'input.scroll': obj({ dx: coord, dy: coord }),
  'input.zoom': obj({ dir: z.enum(['in', 'out']) }),
  'input.absclick': obj({ x: unit, y: unit, monitor: monitorIndex, button: buttonSchema }),
  'key.press': obj({
    key: keyNameSchema,
    modifiers: z.array(modifierSchema).max(4).optional(),
  }),
  'key.text': obj({ text: z.string().min(1).max(2000) }),
  'media.toggle': mediaTarget,
  'media.play': mediaTarget,
  'media.pause': mediaTarget,
  'media.next': mediaTarget,
  'media.prev': mediaTarget,
  'media.seek': obj({
    sessionId: z.string().nullish(),
    to: z.number().min(0).nullish(),
    by: z.number().min(-86_400).max(86_400).nullish(),
  }).refine((p) => (p.to == null) !== (p.by == null), "send exactly one of 'to' or 'by'"),
  'media.select': obj({ sessionId: z.string().min(1) }),
  'media.artwork': obj({ artworkId: z.string().min(1).max(64) }),
  'volume.set': obj({ level }),
  'volume.step': obj({ delta: z.int().min(-100).max(100) }),
  'volume.mute': obj({ muted: z.boolean() }),
  'brightness.set': obj({ level }),
  'power.prepare': obj({ action: powerActionSchema }),
  'power.action': obj({
    action: powerActionSchema,
    confirmToken: z.string().min(1).max(128),
  }),
  'launch.open': obj({ shortcutId: idStr }),
  'scene.run': obj({ sceneId: idStr }),
  'timer.set': obj({
    minutes: z.number().gt(0).max(1440).nullish(),
    mode: timerModeSchema,
    then: timerThenSchema,
  }).refine((p) => p.mode !== 'minutes' || p.minutes != null, 'minutes is required'),
  'timer.cancel': emptySchema,
  'preview.start': obj({
    fps: z.int().min(1).max(15).optional(),
    width: z.int().min(160).max(1920).optional(),
    monitor: monitorIndex.optional(),
  }),
  'preview.stop': emptySchema,
  'preview.ack': obj({ frame: z.int().min(0) }),
  'ai.command': obj({ text: z.string().min(1).max(500) }),
  'ai.confirm': obj({ planId: z.string().min(1).max(64), approve: z.boolean() }),
  'devices.list': emptySchema,
  'devices.revoke': obj({ deviceId: z.string().min(1).max(64) }),
  'devices.role': obj({ deviceId: z.string().min(1).max(64), role: roleSchema }),
  'shortcuts.save': obj({ shortcut: shortcutSchema }),
  'shortcuts.delete': obj({ shortcutId: idStr }),
  'shortcuts.reorder': obj({ ids: z.array(idStr).max(200) }),
  'scenes.save': obj({ scene: sceneSchema }),
  'scenes.delete': obj({ sceneId: idStr }),
  ping: obj({ t: z.number() }),
} as const

export type ClientType = keyof typeof clientPayloads
export type ClientPayload<T extends ClientType> = z.input<(typeof clientPayloads)[T]>

export type RequiredRole = 'none' | 'authed' | 'guest' | 'owner'
export type ReplyKind = 'ack' | 'reply' | 'none'

const g = 'guest' as const
const o = 'owner' as const

export const CLIENT_RULES: Record<ClientType, { role: RequiredRole; reply: ReplyKind }> = {
  'auth.pair': { role: 'none', reply: 'reply' },
  'auth.resume': { role: 'none', reply: 'reply' },
  'input.move': { role: g, reply: 'none' },
  'input.click': { role: o, reply: 'ack' },
  'input.down': { role: o, reply: 'ack' },
  'input.up': { role: o, reply: 'ack' },
  'input.scroll': { role: o, reply: 'none' },
  'input.zoom': { role: o, reply: 'ack' },
  'input.absclick': { role: o, reply: 'ack' },
  'key.press': { role: o, reply: 'ack' },
  'key.text': { role: o, reply: 'ack' },
  'media.toggle': { role: g, reply: 'ack' },
  'media.play': { role: g, reply: 'ack' },
  'media.pause': { role: g, reply: 'ack' },
  'media.next': { role: g, reply: 'ack' },
  'media.prev': { role: g, reply: 'ack' },
  'media.seek': { role: g, reply: 'ack' },
  'media.select': { role: g, reply: 'ack' },
  'media.artwork': { role: g, reply: 'reply' },
  'volume.set': { role: g, reply: 'ack' },
  'volume.step': { role: g, reply: 'ack' },
  'volume.mute': { role: g, reply: 'ack' },
  'brightness.set': { role: o, reply: 'ack' },
  'power.prepare': { role: o, reply: 'reply' },
  'power.action': { role: o, reply: 'ack' },
  'launch.open': { role: o, reply: 'ack' },
  'scene.run': { role: o, reply: 'ack' },
  'timer.set': { role: o, reply: 'ack' },
  'timer.cancel': { role: o, reply: 'ack' },
  'preview.start': { role: o, reply: 'ack' },
  'preview.stop': { role: o, reply: 'ack' },
  'preview.ack': { role: o, reply: 'none' },
  'ai.command': { role: o, reply: 'reply' },
  'ai.confirm': { role: o, reply: 'ack' },
  'devices.list': { role: o, reply: 'reply' },
  'devices.revoke': { role: o, reply: 'ack' },
  'devices.role': { role: o, reply: 'ack' },
  'shortcuts.save': { role: o, reply: 'ack' },
  'shortcuts.delete': { role: o, reply: 'ack' },
  'shortcuts.reorder': { role: o, reply: 'ack' },
  'scenes.save': { role: o, reply: 'ack' },
  'scenes.delete': { role: o, reply: 'ack' },
  ping: { role: 'authed', reply: 'reply' },
}

// ---------------------------------------------------------------- agent -> client payloads

export const agentPayloads = {
  ack: obj({ id: z.string(), ok: z.boolean(), error: z.string().nullish() }),
  'auth.ok': obj({
    deviceId: z.string(),
    token: z.string().nullish(),
    role: roleSchema,
    hostName: z.string(),
    os: osSchema,
    features: featuresSchema,
  }),
  'auth.fail': obj({ reason: authFailReasonSchema }),
  'media.state': obj({
    sessions: z.array(mediaSessionSchema),
    currentId: z.string().nullable(),
    ts: timestamp,
  }),
  'media.artwork': obj({ artworkId: z.string(), artwork: z.string().nullable() }),
  'context.state': obj({
    app: z.string(),
    processName: z.string(),
    windowTitle: z.string(),
    category: contextCategorySchema,
    site: siteSchema.nullable(),
    ts: timestamp,
  }),
  'volume.state': obj({ level, muted: z.boolean() }),
  'brightness.state': obj({ level: level.nullable(), supported: z.boolean() }),
  'timer.state': obj({
    active: z.boolean(),
    endsAt: timestamp.nullable(),
    mode: timerModeSchema.nullable(),
    then: timerThenSchema.nullable(),
  }),
  'preview.meta': obj({
    width: z.int(),
    height: z.int(),
    monitors: z.array(monitorInfoSchema),
  }),
  'ai.plan': obj({
    planId: z.string(),
    reply: z.string(),
    actions: z.array(aiActionSchema),
    needsConfirm: z.boolean(),
  }),
  'ai.result': obj({ planId: z.string(), steps: z.array(aiStepResultSchema) }),
  toast: obj({ level: toastLevelSchema, message: z.string().max(300) }),
  pong: obj({ t: z.number() }),
  'devices.state': obj({ devices: z.array(deviceInfoSchema) }),
  'power.token': obj({
    action: powerActionSchema,
    confirmToken: z.string(),
    expiresAt: timestamp,
  }),
  'shortcuts.state': obj({ shortcuts: z.array(shortcutSchema) }),
  'scenes.state': obj({ scenes: z.array(sceneSchema) }),
} as const

export type AgentType = keyof typeof agentPayloads
export type AgentPayload<T extends AgentType> = z.output<(typeof agentPayloads)[T]>
export type AgentMessage = {
  [K in AgentType]: { v: 1; id: string; type: K; payload: AgentPayload<K> }
}[AgentType]

const envelopeSchema = z.object({
  v: z.literal(PROTOCOL_VERSION),
  id: z.string().max(64),
  type: z.string().min(1).max(64),
  payload: z.unknown(),
})

/** Parse and validate one JSON frame from the agent. Returns null for anything invalid. */
export function parseAgentMessage(text: string): AgentMessage | null {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  const envelope = envelopeSchema.safeParse(raw)
  if (!envelope.success) return null
  const { type, id, payload } = envelope.data
  if (!(type in agentPayloads)) return null
  const schema = agentPayloads[type as AgentType]
  const parsed = schema.safeParse(payload)
  if (!parsed.success) return null
  return { v: 1, id, type, payload: parsed.data } as AgentMessage
}

export function encodeClientMessage<T extends ClientType>(
  type: T,
  payload: ClientPayload<T>,
  id: string,
): string {
  return JSON.stringify({ v: PROTOCOL_VERSION, id, type, payload })
}

/** Preview frames: 8-byte big-endian header (uint32 frame, uint32 monitor) then JPEG. */
export const PREVIEW_HEADER_BYTES = 8
