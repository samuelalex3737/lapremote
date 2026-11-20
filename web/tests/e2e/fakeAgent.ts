/**
 * A scripted stand-in for the agent, served through page.routeWebSocket, so UI
 * behaviour (adaptive modes, banners, scrubbing) can be tested deterministically
 * without depending on what happens to be playing on the laptop.
 */
import { readFileSync } from 'node:fs'
import type { Page, WebSocketRoute } from '@playwright/test'
import { DEFAULT_LAYOUTS } from './defaultLayouts.ts'

export const FRAME_JPEG = readFileSync(new URL('./frame-480x270.jpg', import.meta.url))

export const RED_JPEG =
  'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDyqiiivij+6z//2Q=='

const FEATURE = { available: true, reason: null }

export const FEATURES = {
  input: FEATURE,
  media: FEATURE,
  volume: FEATURE,
  brightness: FEATURE,
  preview: FEATURE,
  context: FEATURE,
  power: FEATURE,
  launcher: FEATURE,
  scenes: FEATURE,
  timer: FEATURE,
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

export const DEFAULT_SHORTCUTS = [{"id": "netflix", "name": "Netflix", "kind": "url", "url": "https://www.netflix.com/browse", "icon": "netflix"}, {"id": "youtube", "name": "YouTube", "kind": "url", "url": "https://www.youtube.com/", "icon": "youtube"}, {"id": "youtube-music", "name": "YouTube Music", "kind": "url", "url": "https://music.youtube.com/", "icon": "music"}, {"id": "prime-video", "name": "Prime Video", "kind": "url", "url": "https://www.primevideo.com/", "icon": "prime"}, {"id": "spotify", "name": "Spotify", "kind": "url", "url": "https://open.spotify.com/", "icon": "spotify"}]
export const DEFAULT_SCENES = [{"id": "movie-night", "name": "Movie Night", "steps": [{"type": "volume.set", "level": 40}, {"type": "brightness.set", "level": 60}, {"type": "launch.open", "shortcutId": "netflix"}]}, {"id": "focus-music", "name": "Focus Music", "steps": [{"type": "launch.open", "shortcutId": "youtube-music"}, {"type": "volume.set", "level": 25}]}]

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
  shortcuts: { id: string }[] = structuredClone(DEFAULT_SHORTCUTS)
  scenes: { id: string }[] = structuredClone(DEFAULT_SCENES)
  timer: Record<string, unknown> = { active: false, endsAt: null, mode: null, then: null }
  layouts: { id: string }[] = structuredClone(DEFAULT_LAYOUTS)
  peers: Record<string, unknown>[] = []
  laptopClipboard = 'text on the laptop'
  apps = [
    { appId: 'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify', name: 'Spotify' },
    { appId: 'VideoLAN.VLC', name: 'VLC media player' },
    { appId: 'Microsoft.WindowsNotepad_8wekyb3d8bbwe!App', name: 'Notepad' },
  ]

  /** Scripted AI plans by request text. Unknown requests get a "can't do that" reply. */
  aiPlans: Record<string, { reply: string; actions: { type: string; payload: Record<string, unknown> }[]; needsConfirm: boolean }> = {}
  private planSeq = 0

  constructor(private readonly initial: { sessions: unknown[]; context: unknown; ai?: boolean }) {}

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
        this.push('auth.ok', { deviceId: 'fake', token: null, role: 'owner', hostName: 'TEST-LAPTOP', os: 'windows', features: this.initial.ai === true ? { ...FEATURES, ai: FEATURE } : FEATURES })
        this.push('media.state', { sessions: this.initial.sessions, currentId: 'w1', ts: Date.now() })
        this.push('volume.state', { level: 35, muted: false })
        if (this.initial.context !== null) this.push('context.state', this.initial.context)
        this.push('shortcuts.state', { shortcuts: this.shortcuts })
        this.push('scenes.state', { scenes: this.scenes })
        this.push('timer.state', this.timer)
        this.push('brightness.state', { level: 70, supported: true })
        this.push('layouts.state', { layouts: this.layouts })
        this.push('peers.state', { peers: this.peers })
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
      case 'shortcuts.save': {
        const s = msg.payload.shortcut as { id: string }
        this.shortcuts = [...this.shortcuts.filter((x) => x.id !== s.id), s]
        this.push('shortcuts.state', { shortcuts: this.shortcuts })
        break
      }
      case 'shortcuts.delete':
        this.shortcuts = this.shortcuts.filter((x) => x.id !== msg.payload.shortcutId)
        this.push('shortcuts.state', { shortcuts: this.shortcuts })
        break
      case 'scenes.save': {
        const s = msg.payload.scene as { id: string }
        this.scenes = [...this.scenes.filter((x) => x.id !== s.id), s]
        this.push('scenes.state', { scenes: this.scenes })
        break
      }
      case 'timer.set':
        this.timer = { active: true, endsAt: Date.now() + Number(msg.payload.minutes ?? 1) * 60_000, mode: msg.payload.mode, then: msg.payload.then }
        this.push('timer.state', this.timer)
        break
      case 'timer.cancel':
        this.timer = { active: false, endsAt: null, mode: null, then: null }
        this.push('timer.state', this.timer)
        break
      case 'clipboard.set':
        this.laptopClipboard = String(msg.payload.text)
        break
      case 'clipboard.get':
        this.push('clipboard.state', { text: this.laptopClipboard, ts: Date.now() })
        return
      case 'apps.list':
        this.push('apps.state', { apps: this.apps })
        return
      case 'layouts.save': {
        const l = msg.payload.layout as { id: string }
        this.layouts = [...this.layouts.filter((x) => x.id !== l.id), l]
        this.push('layouts.state', { layouts: this.layouts })
        break
      }
      case 'layouts.delete':
        this.layouts = this.layouts.filter((x) => x.id !== msg.payload.layoutId)
        this.push('layouts.state', { layouts: this.layouts })
        break
      case 'ai.command': {
        this.planSeq += 1
        const planId = `plan-${String(this.planSeq)}`
        const text = String(msg.payload.text)
        const plan = this.aiPlans[text] ?? { reply: "I can't do that.", actions: [], needsConfirm: false }
        this.push('ai.plan', { planId, ...plan })
        if (!plan.needsConfirm && plan.actions.length > 0) {
          this.push('ai.result', { planId, steps: plan.actions.map((a) => ({ type: a.type, ok: true, error: null })) })
        }
        return
      }
      case 'ai.confirm': {
        this.push('ack', { id: msg.id, ok: true, error: null })
        if (msg.payload.approve === true) {
          this.push('ai.result', { planId: msg.payload.planId, steps: [{ type: 'power.action', ok: true, error: null }] })
        }
        return
      }
      case 'power.prepare':
        this.push('power.token', { action: msg.payload.action, confirmToken: 'tok-123', expiresAt: Date.now() + 10_000 })
        return
      case 'brightness.set':
        this.push('brightness.state', { level: msg.payload.level, supported: true })
        break
      default:
        break
    }
    if (msg.type !== 'input.move' && msg.type !== 'input.scroll') {
      this.push('ack', { id: msg.id, ok: true, error: null })
    }
  }

  of(type: string): Sent[] {
    return this.sent.filter((s) => s.type === type)
  }
}
