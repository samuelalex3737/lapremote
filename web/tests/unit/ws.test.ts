import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { memoryCredentialStore } from '../../src/lib/credentials.ts'
import {
  backoffDelay,
  isRealtime,
  RemoteClient,
  RequestError,
  type SocketLike,
} from '../../src/lib/ws.ts'

class FakeSocket implements SocketLike {
  static all: FakeSocket[] = []
  readyState = 0
  sent: { id: string; type: string; payload: Record<string, unknown> }[] = []
  closedWith: number | null = null
  onopen: (() => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(readonly url: string) {
    FakeSocket.all.push(this)
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data) as FakeSocket['sent'][number])
  }

  close(code = 1000): void {
    this.closedWith = code
  }

  open(): void {
    this.readyState = 1
    this.onopen?.()
  }

  deliver(type: string, payload: unknown, id = 's1'): void {
    this.onmessage?.({ data: JSON.stringify({ v: 1, id, type, payload }) })
  }

  drop(code = 1006): void {
    this.readyState = 3
    this.onclose?.({ code })
  }

  last(type: string) {
    return [...this.sent].reverse().find((m) => m.type === type)
  }
}

const features = {
  input: { available: false, reason: 'x' },
  media: { available: false, reason: null },
  volume: { available: false },
  brightness: { available: false },
  preview: { available: false },
  context: { available: false },
  power: { available: false },
  launcher: { available: false },
  scenes: { available: false },
  timer: { available: false },
  ai: { available: false },
  secureContext: false,
}

function authOk(token: string | null = null, role = 'owner') {
  return { deviceId: 'dev1', token, role, hostName: 'LAPTOP', os: 'windows', features }
}

function makeClient(creds: { deviceId: string; token: string } | null = null) {
  const store = memoryCredentialStore(creds)
  let clock = 1000
  const client = new RemoteClient({
    url: 'ws://laptop/ws',
    store,
    createSocket: (url) => new FakeSocket(url),
    deviceName: 'iPhone',
    platform: 'ios',
    now: () => clock,
  })
  return {
    client,
    store,
    socket: () => {
      const s = FakeSocket.all.at(-1)
      if (s === undefined) throw new Error('no socket yet')
      return s
    },
    tick: (ms: number) => {
      clock += ms
    },
  }
}

beforeEach(() => {
  FakeSocket.all = []
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('backoff', () => {
  it('doubles from 0.5s and caps at 5s', () => {
    expect([0, 1, 2, 3, 4, 5].map(backoffDelay)).toEqual([500, 1000, 2000, 4000, 5000, 5000])
  })
})

describe('pairing', () => {
  it('waits on the pairing screen without credentials', () => {
    const { client } = makeClient()
    client.start()
    expect(client.getSnapshot().status).toEqual({ kind: 'unpaired', error: null })
    expect(FakeSocket.all).toHaveLength(0)
  })

  it('pairs, stores the token and starts pinging', () => {
    const { client, store, socket } = makeClient()
    client.pair('123456')
    expect(client.getSnapshot().status.kind).toBe('pairing')
    socket().open()
    expect(socket().sent[0]).toMatchObject({
      type: 'auth.pair',
      payload: { code: '123456', deviceName: 'iPhone', platform: 'ios' },
    })
    socket().deliver('auth.ok', authOk('tok-123'))
    expect(store.load()).toEqual({ deviceId: 'dev1', token: 'tok-123' })
    const snap = client.getSnapshot()
    expect(snap.status.kind).toBe('connected')
    expect(snap.session?.hostName).toBe('LAPTOP')
    expect(socket().last('ping')).toBeDefined()
  })

  it.each(['invalid_code', 'expired_code', 'rate_limited'] as const)(
    'shows %s and does not retry',
    (reason) => {
      const { client, socket } = makeClient()
      client.pair('111111')
      socket().open()
      socket().deliver('auth.fail', { reason })
      expect(client.getSnapshot().status).toEqual({ kind: 'unpaired', error: reason })
      vi.advanceTimersByTime(10_000)
      expect(FakeSocket.all).toHaveLength(1)
    },
  )
})

describe('resume and reconnect', () => {
  it('resumes with saved credentials', () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().open()
    expect(socket().sent[0]).toMatchObject({
      type: 'auth.resume',
      payload: { deviceId: 'dev1', token: 'tok' },
    })
    socket().deliver('auth.ok', authOk())
    expect(client.getSnapshot().status.kind).toBe('connected')
  })

  it('reconnects with exponential backoff and resets after success', () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().open()
    socket().deliver('auth.ok', authOk())
    socket().drop()
    expect(client.getSnapshot().status).toEqual({ kind: 'offline', retryInMs: 500 })
    vi.advanceTimersByTime(499)
    expect(FakeSocket.all).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeSocket.all).toHaveLength(2)
    socket().drop()
    expect(client.getSnapshot().status).toEqual({ kind: 'offline', retryInMs: 1000 })
    vi.advanceTimersByTime(1000)
    socket().open()
    socket().deliver('auth.ok', authOk())
    socket().drop()
    expect(client.getSnapshot().status).toEqual({ kind: 'offline', retryInMs: 500 })
  })

  it('reconnectNow skips the wait', () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().drop()
    client.reconnectNow()
    expect(FakeSocket.all).toHaveLength(2)
  })

  it('forgets credentials on bad_token', () => {
    const { client, store, socket } = makeClient({ deviceId: 'dev1', token: 'old' })
    client.start()
    socket().open()
    socket().deliver('auth.fail', { reason: 'bad_token' })
    expect(store.load()).toBeNull()
    expect(client.getSnapshot().status).toEqual({ kind: 'unpaired', error: 'bad_token' })
  })

  it('forgets credentials when revoked', () => {
    const { client, store, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().open()
    socket().deliver('auth.ok', authOk())
    socket().drop(4003)
    expect(store.load()).toBeNull()
    expect(client.getSnapshot().status).toEqual({ kind: 'unpaired', error: 'revoked' })
  })
})

describe('sending', () => {
  it('drops input while offline and replays queued commands after auth', () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    expect(client.send('input.move', { dx: 1, dy: 1 })).toBeNull()
    expect(client.send('media.toggle', {})).not.toBeNull()
    socket().open()
    expect(socket().sent.map((m) => m.type)).toEqual(['auth.resume'])
    socket().deliver('auth.ok', authOk())
    expect(socket().sent.map((m) => m.type)).toEqual(['auth.resume', 'media.toggle', 'ping'])
  })

  it('caps the offline queue', () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    for (let i = 0; i < 60; i++) client.send('volume.set', { level: i })
    socket().open()
    socket().deliver('auth.ok', authOk())
    const volumes = socket().sent.filter((m) => m.type === 'volume.set')
    expect(volumes).toHaveLength(50)
    expect(volumes[0]?.payload).toEqual({ level: 10 })
  })

  it('resolves requests on ack and rejects with the agent error', async () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().open()
    socket().deliver('auth.ok', authOk())
    const ok = client.request('volume.set', { level: 30 })
    const okId = socket().last('volume.set')?.id ?? ''
    socket().deliver('ack', { id: okId, ok: true })
    await expect(ok).resolves.toMatchObject({ type: 'ack' })

    const bad = client.request('brightness.set', { level: 30 })
    const badId = socket().last('brightness.set')?.id ?? ''
    socket().deliver('ack', { id: badId, ok: false, error: 'Only the owner can do that.' })
    await expect(bad).rejects.toThrow('Only the owner can do that.')
  })

  it('resolves reply-type requests on their reply message', async () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().open()
    socket().deliver('auth.ok', authOk())
    const pending = client.request('devices.list', {})
    socket().deliver('devices.state', { devices: [] })
    await expect(pending).resolves.toMatchObject({ type: 'devices.state' })
  })

  it('times out requests', async () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().open()
    socket().deliver('auth.ok', authOk())
    const pending = client.request('volume.set', { level: 1 }, 1000)
    vi.advanceTimersByTime(1000)
    await expect(pending).rejects.toBeInstanceOf(RequestError)
  })

  it('rejects requests while offline', async () => {
    const { client } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    await expect(client.request('volume.set', { level: 1 })).rejects.toThrow(
      "Can't reach your laptop right now.",
    )
  })

  it('measures latency from pongs', () => {
    const { client, socket, tick } = makeClient({ deviceId: 'dev1', token: 'tok' })
    client.start()
    socket().open()
    socket().deliver('auth.ok', authOk())
    const t = socket().last('ping')?.payload.t as number
    tick(14)
    socket().deliver('pong', { t })
    expect(client.getSnapshot().latencyMs).toBe(14)
  })

  it('ignores invalid frames and notifies handlers', () => {
    const { client, socket } = makeClient({ deviceId: 'dev1', token: 'tok' })
    const toasts: string[] = []
    client.on('toast', (p) => toasts.push(p.message))
    client.start()
    socket().open()
    socket().onmessage?.({ data: 'garbage' })
    socket().deliver('toast', { level: 'info', message: 'Hi' })
    expect(toasts).toEqual(['Hi'])
  })
})

describe('isRealtime', () => {
  it('flags input, preview and ping', () => {
    expect(isRealtime('input.move')).toBe(true)
    expect(isRealtime('preview.ack')).toBe(true)
    expect(isRealtime('ping')).toBe(true)
    expect(isRealtime('media.toggle')).toBe(false)
  })
})
