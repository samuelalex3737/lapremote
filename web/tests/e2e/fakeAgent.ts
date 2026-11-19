/**
 * A scripted stand-in for the agent, served through page.routeWebSocket, so UI
 * behaviour (adaptive modes, banners, scrubbing) can be tested deterministically
 * without depending on what happens to be playing on the laptop.
 */
import { readFileSync } from 'node:fs'
import type { Page, WebSocketRoute } from '@playwright/test'

export const FRAME_JPEG = readFileSync(new URL('./frame-480x270.jpg', import.meta.url))

export const RED_JPEG =
  'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDyqiiivij+6z//2Q=='

const FEATURE = { available: true, reason: null }

export const FEATURES = {
  input: FEATURE,
  media: FEATURE,
  volume: FEATURE,
  brightness: { available: false, reason: 'Not available in this version yet.' },
  preview: FEATURE,
  context: FEATURE,
  power: { available: false, reason: 'Not available in this version yet.' },
  launcher: { available: false, reason: 'Not available in this version yet.' },
  scenes: { available: false, reason: 'Not available in this version yet.' },
  timer: { available: false, reason: 'Not available in this version yet.' },
  ai: { available: false, reason: 'Not available in this version yet.' },
  secureContext: false,
}

export function session(patch: Record<string, unknown> = {}) {
  return {
    id: 'w1',
    appId: 'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify',
    appName: 'Spotify',
    title: 'Midnight City',
    artist: 'M83',
    album: 'Hurry Up',
    artworkId: 'red16',
    artwork: RED_JPEG,
    status: 'playing',
    position: 60,
    duration: 240,
    rate: 1,
    canSeek: true,
    canNext: true,
    canPrev: true,
    updatedAt: Date.now(),
    ...patch,
  }
}

export function context(patch: Record<string, unknown> = {}) {
  return {
    app: 'Brave',
    processName: 'brave.exe',
    windowTitle: 'Stranger Things | Netflix - Brave',
    category: 'browser',
    site: 'netflix',
    ts: Date.now(),
    ...patch,
  }
}

interface Sent {
  type: string
  payload: Record<string, unknown>
}

export class FakeAgent {
  readonly sent: Sent[] = []
  private ws: WebSocketRoute | null = null
  private seq = 0

  /** Monitors reported in preview.meta. */
  monitors = [{ index: 0, left: 0, top: 0, width: 1920, height: 1080, primary: true }]
  private frameNo = 0

  constructor(private readonly initial: { sessions: unknown[]; context: unknown }) {}

  /** Send one binary preview frame: 8-byte big-endian header then the JPEG. */
  pushFrame(monitor = 0): number {
    this.frameNo += 1
    const header = Buffer.alloc(8)
    header.writeUInt32BE(this.frameNo, 0)
    header.writeUInt32BE(monitor, 4)
    this.ws?.send(Buffer.concat([header, FRAME_JPEG]))
    return this.frameNo
  }

  async install(page: Page): Promise<void> {
    await page.addInitScript(() => {
      localStorage.setItem('lapremote.credentials.v1', JSON.stringify({ deviceId: 'fake', token: 'fake-token' }))
      sessionStorage.setItem('lapremote.hintsSeen', '1')
    })
    await page.routeWebSocket('**/ws', (ws) => {
      this.ws = ws
      ws.onMessage((raw) => {
        const msg = JSON.parse(String(raw)) as { id: string; type: string; payload: Record<string, unknown> }
        this.sent.push({ type: msg.type, payload: msg.payload })
        this.reply(msg)
      })
    })
  }

  push(type: string, payload: unknown): void {
    this.seq += 1
    this.ws?.send(JSON.stringify({ v: 1, id: `f${String(this.seq)}`, type, payload }))
  }

  private reply(msg: { id: string; type: string; payload: Record<string, unknown> }): void {
    switch (msg.type) {
      case 'auth.resume':
        this.push('auth.ok', { deviceId: 'fake', token: null, role: 'owner', hostName: 'TEST-LAPTOP', os: 'windows', features: FEATURES })
        this.push('media.state', { sessions: this.initial.sessions, currentId: 'w1', ts: Date.now() })
        this.push('volume.state', { level: 35, muted: false })
        if (this.initial.context !== null) this.push('context.state', this.initial.context)
        return
      case 'ping':
        this.push('pong', { t: msg.payload.t })
        return
      case 'preview.start':
        this.push('preview.meta', { width: 480, height: 270, monitors: this.monitors })
        this.push('ack', { id: msg.id, ok: true, error: null })
        this.pushFrame(Number(msg.payload.monitor ?? 0))
        return
      case 'preview.ack':
        return
      default:
        if (msg.type !== 'input.move' && msg.type !== 'input.scroll') {
          this.push('ack', { id: msg.id, ok: true, error: null })
        }
    }
  }

  of(type: string): Sent[] {
    return this.sent.filter((s) => s.type === type)
  }
}
