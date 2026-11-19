/**
 * The phone's connection to the agent: pairing, resume, reconnect with backoff,
 * acks, a small offline queue for non-input commands, and latency pings.
 */
import type { CredentialStore } from './credentials.ts'
import {
  type AgentMessage,
  type AgentPayload,
  type AgentType,
  type ClientPayload,
  type ClientType,
  encodeClientMessage,
  type Features,
  parseAgentMessage,
} from './protocol.ts'

export const BACKOFF_START_MS = 500
export const BACKOFF_MAX_MS = 5000
export const PING_INTERVAL_MS = 2000
export const REQUEST_TIMEOUT_MS = 5000
export const MAX_QUEUE = 50
const CLOSE_REVOKED = 4003

export interface SocketLike {
  readonly readyState: number
  send(data: string): void
  close(code?: number, reason?: string): void
  onopen: (() => void) | null
  onclose: ((event: { code: number }) => void) | null
  onmessage: ((event: { data: unknown }) => void) | null
  onerror: (() => void) | null
}

export type SocketFactory = (url: string) => SocketLike

export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(handle: unknown): void
  setInterval(fn: () => void, ms: number): unknown
  clearInterval(handle: unknown): void
}

const browserTimers: Timers = {
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (h) => {
    globalThis.clearTimeout(h as ReturnType<typeof setTimeout>)
  },
  setInterval: (fn, ms) => globalThis.setInterval(fn, ms),
  clearInterval: (h) => {
    globalThis.clearInterval(h as ReturnType<typeof setInterval>)
  },
}

export type PairError = 'invalid_code' | 'expired_code' | 'rate_limited' | 'bad_token' | 'revoked'

export type Status =
  | { kind: 'unpaired'; error: PairError | null }
  | { kind: 'pairing' }
  | { kind: 'connecting'; attempt: number }
  | { kind: 'connected' }
  | { kind: 'offline'; retryInMs: number }

export interface Session {
  deviceId: string
  role: 'owner' | 'guest'
  hostName: string
  os: 'windows' | 'macos' | 'linux'
  features: Features
}

export interface Snapshot {
  status: Status
  session: Session | null
  latencyMs: number | null
}

export interface ClientOptions {
  url: string
  store: CredentialStore
  createSocket: SocketFactory
  deviceName: string
  platform: string
  timers?: Timers
  now?: () => number
}

export class RequestError extends Error {
  override name = 'RequestError'
}

/** The reply message type for requests answered with a dedicated message instead of an ack. */
const REPLY_TYPES: Partial<Record<ClientType, AgentType>> = {
  ping: 'pong',
  'media.artwork': 'media.artwork',
  'power.prepare': 'power.token',
  'devices.list': 'devices.state',
  'ai.command': 'ai.plan',
}

/** Messages that are pointless to replay later: input happens now or never. */
export function isRealtime(type: ClientType): boolean {
  return type.startsWith('input.') || type.startsWith('preview.') || type === 'ping'
}

export function backoffDelay(attempt: number): number {
  return Math.min(BACKOFF_START_MS * 2 ** attempt, BACKOFF_MAX_MS)
}

interface Pending {
  id: string
  replyType: AgentType | null
  resolve: (message: AgentMessage) => void
  reject: (error: Error) => void
  timer: unknown
}

type Handler<T extends AgentType> = (payload: AgentPayload<T>) => void

export class RemoteClient {
  private readonly opts: ClientOptions
  private readonly timers: Timers
  private readonly now: () => number
  private socket: SocketLike | null = null
  private snapshot: Snapshot = { status: { kind: 'unpaired', error: null }, session: null, latencyMs: null }
  private readonly listeners = new Set<() => void>()
  private readonly handlers = new Map<AgentType, Set<(payload: unknown) => void>>()
  private readonly binaryHandlers = new Set<(data: ArrayBuffer) => void>()
  private readonly pending = new Map<string, Pending>()
  private queue: string[] = []
  private attempt = 0
  private seq = 0
  private pairCode: string | null = null
  private retryTimer: unknown = null
  private pingTimer: unknown = null
  private stopped = false
  private authed = false

  constructor(opts: ClientOptions) {
    this.opts = opts
    this.timers = opts.timers ?? browserTimers
    this.now = opts.now ?? (() => performance.now())
  }

  // ------------------------------------------------------------- state

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  readonly getSnapshot = (): Snapshot => this.snapshot

  private update(patch: Partial<Snapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch }
    for (const listener of this.listeners) listener()
  }

  on<T extends AgentType>(type: T, handler: Handler<T>): () => void {
    let set = this.handlers.get(type)
    if (set === undefined) {
      set = new Set()
      this.handlers.set(type, set)
    }
    const wrapped = handler as (payload: unknown) => void
    set.add(wrapped)
    return () => set.delete(wrapped)
  }

  /** Binary frames (screen preview). The socket must use binaryType 'arraybuffer'. */
  onBinary(handler: (data: ArrayBuffer) => void): () => void {
    this.binaryHandlers.add(handler)
    return () => this.binaryHandlers.delete(handler)
  }

  // ------------------------------------------------------------- lifecycle

  /** Connect with saved credentials, or wait on the pairing screen if there are none. */
  start(): void {
    this.stopped = false
    if (this.socket !== null) return
    if (this.opts.store.load() === null) {
      this.update({ status: { kind: 'unpaired', error: null } })
      return
    }
    this.open()
  }

  pair(code: string): void {
    this.stopped = false
    this.pairCode = code
    this.update({ status: { kind: 'pairing' } })
    this.closeSocket()
    this.open()
  }

  /** Reconnect right away (for example when the phone comes back online or is unlocked). */
  reconnectNow(): void {
    if (this.stopped || this.snapshot.status.kind !== 'offline') return
    this.clearRetry()
    this.open()
  }

  stop(): void {
    this.stopped = true
    this.clearRetry()
    this.closeSocket()
  }

  /** Forget this laptop on the phone side. */
  forget(error: PairError | null = null): void {
    this.opts.store.clear()
    this.stop()
    this.queue = []
    this.update({ status: { kind: 'unpaired', error }, session: null, latencyMs: null })
  }

  private open(): void {
    this.authed = false
    if (this.snapshot.status.kind !== 'pairing') {
      this.update({ status: { kind: 'connecting', attempt: this.attempt } })
    }
    const socket = this.opts.createSocket(this.opts.url)
    this.socket = socket
    socket.onopen = () => {
      if (socket === this.socket) this.authenticate()
    }
    socket.onmessage = (event) => {
      if (socket !== this.socket) return
      if (typeof event.data === 'string') this.receive(event.data)
      else if (event.data instanceof ArrayBuffer) {
        for (const handler of this.binaryHandlers) handler(event.data)
      }
    }
    socket.onclose = (event) => {
      if (socket === this.socket) this.closed(event.code)
    }
    socket.onerror = () => {
      // onclose always follows and handles the retry.
    }
  }

  private authenticate(): void {
    const creds = this.opts.store.load()
    if (this.pairCode !== null) {
      this.raw('auth.pair', {
        code: this.pairCode,
        deviceName: this.opts.deviceName,
        platform: this.opts.platform,
      })
    } else if (creds !== null) {
      this.raw('auth.resume', creds)
    } else {
      this.forget(null)
    }
  }

  private closeSocket(): void {
    const socket = this.socket
    this.socket = null
    this.stopPing()
    this.failPending('Disconnected')
    if (socket !== null) {
      socket.onopen = null
      socket.onmessage = null
      socket.onclose = null
      socket.onerror = null
      try {
        socket.close(1000, 'client closing')
      } catch {
        // Already closed.
      }
    }
  }

  private closed(code: number): void {
    const wasAuthed = this.authed
    this.socket = null
    this.authed = false
    this.stopPing()
    this.failPending('Disconnected')
    if (this.stopped || this.snapshot.status.kind === 'unpaired') return
    if (code === CLOSE_REVOKED && wasAuthed) {
      this.forget('revoked')
      return
    }
    if (this.pairCode !== null && !wasAuthed) {
      // Pairing never got an answer: let the person try again instead of looping.
      this.pairCode = null
      this.update({ status: { kind: 'unpaired', error: null } })
      return
    }
    const delay = backoffDelay(this.attempt)
    this.attempt += 1
    this.update({ status: { kind: 'offline', retryInMs: delay }, latencyMs: null })
    this.clearRetry()
    this.retryTimer = this.timers.setTimeout(() => {
      this.retryTimer = null
      this.open()
    }, delay)
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) {
      this.timers.clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
  }

  // ------------------------------------------------------------- receiving

  private receive(text: string): void {
    const message = parseAgentMessage(text)
    if (message === null) return
    switch (message.type) {
      case 'auth.ok':
        this.authenticated(message.payload)
        break
      case 'auth.fail':
        this.authFailed(message.payload.reason)
        break
      case 'pong':
        this.update({ latencyMs: Math.max(0, Math.round(this.now() - message.payload.t)) })
        break
      default:
        break
    }
    this.settle(message)
    const set = this.handlers.get(message.type)
    if (set !== undefined) {
      for (const handler of set) handler(message.payload)
    }
  }

  private authenticated(payload: AgentPayload<'auth.ok'>): void {
    if (payload.token != null) {
      this.opts.store.save({ deviceId: payload.deviceId, token: payload.token })
    }
    this.pairCode = null
    this.authed = true
    this.attempt = 0
    this.update({
      status: { kind: 'connected' },
      session: {
        deviceId: payload.deviceId,
        role: payload.role,
        hostName: payload.hostName,
        os: payload.os,
        features: payload.features,
      },
    })
    const queued = this.queue
    this.queue = []
    for (const text of queued) this.socket?.send(text)
    this.startPing()
  }

  private authFailed(reason: AgentPayload<'auth.fail'>['reason']): void {
    if (reason === 'bad_token') {
      this.forget('bad_token')
      return
    }
    this.pairCode = null
    this.stop()
    this.update({ status: { kind: 'unpaired', error: reason } })
  }

  private settle(message: AgentMessage): void {
    if (message.type === 'ack') {
      const pending = this.pending.get(message.payload.id)
      if (pending === undefined) return
      this.dropPending(pending)
      if (message.payload.ok) pending.resolve(message)
      else pending.reject(new RequestError(message.payload.error ?? 'That did not work.'))
      return
    }
    for (const pending of this.pending.values()) {
      if (pending.replyType === message.type) {
        this.dropPending(pending)
        pending.resolve(message)
        return
      }
    }
  }

  private dropPending(pending: Pending): void {
    this.timers.clearTimeout(pending.timer)
    this.pending.delete(pending.id)
  }

  private failPending(reason: string): void {
    for (const pending of [...this.pending.values()]) {
      this.dropPending(pending)
      pending.reject(new RequestError(reason))
    }
  }

  // ------------------------------------------------------------- sending

  private nextId(): string {
    this.seq += 1
    return `c${String(this.seq)}`
  }

  private raw<T extends ClientType>(type: T, payload: ClientPayload<T>): void {
    this.socket?.send(encodeClientMessage(type, payload, this.nextId()))
  }

  /**
   * Send a message. Returns its id, or null if it was dropped (input while offline).
   * Non-input messages sent while offline are queued and replayed after reconnecting.
   */
  send<T extends ClientType>(type: T, payload: ClientPayload<T>): string | null {
    const id = this.nextId()
    const text = encodeClientMessage(type, payload, id)
    if (this.authed && this.socket !== null) {
      this.socket.send(text)
      return id
    }
    if (isRealtime(type)) return null
    this.queue.push(text)
    if (this.queue.length > MAX_QUEUE) this.queue.shift()
    return id
  }

  /** Send and wait for the ack (or the reply message). Rejects with a friendly RequestError. */
  request<T extends ClientType>(
    type: T,
    payload: ClientPayload<T>,
    timeoutMs = REQUEST_TIMEOUT_MS,
  ): Promise<AgentMessage> {
    return new Promise((resolve, reject) => {
      if (!this.authed) {
        reject(new RequestError("Can't reach your laptop right now."))
        return
      }
      const id = this.send(type, payload)
      if (id === null) {
        reject(new RequestError("Can't reach your laptop right now."))
        return
      }
      const pending: Pending = {
        id,
        replyType: REPLY_TYPES[type] ?? null,
        resolve,
        reject,
        timer: this.timers.setTimeout(() => {
          this.pending.delete(id)
          reject(new RequestError('Your laptop took too long to answer.'))
        }, timeoutMs),
      }
      this.pending.set(id, pending)
    })
  }

  private startPing(): void {
    this.stopPing()
    const ping = () => {
      if (this.authed) this.raw('ping', { t: this.now() })
    }
    ping()
    this.pingTimer = this.timers.setInterval(ping, PING_INTERVAL_MS)
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      this.timers.clearInterval(this.pingTimer)
      this.pingTimer = null
    }
  }
}
