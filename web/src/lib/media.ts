/**
 * Phone-side media state: artwork cache keyed by artworkId and position
 * interpolation from updatedAt and rate (the seek bar is never polled).
 */
import type { AgentPayload, MediaSession } from './protocol.ts'

export interface MediaView {
  sessions: MediaSession[]
  currentId: string | null
}

/** Position in seconds at wall-clock time `nowMs`, clamped to the duration. */
export function positionAt(session: MediaSession, nowMs: number): number | null {
  if (session.position === null) return null
  if (session.status !== 'playing') return session.position
  const elapsed = Math.max(0, (nowMs - session.updatedAt) / 1000)
  const value = session.position + elapsed * session.rate
  return session.duration !== null ? Math.min(value, session.duration) : value
}

export function formatTime(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '--:--'
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const mm = h > 0 ? String(m).padStart(2, '0') : String(m)
  return `${h > 0 ? `${String(h)}:` : ''}${mm}:${String(s).padStart(2, '0')}`
}

/**
 * Keeps artwork images by id. The agent sends each image once per connection,
 * so the phone remembers it and asks (media.artwork) only for ids it has never seen.
 */
export class ArtworkCache {
  private readonly images = new Map<string, string>()
  private readonly requested = new Set<string>()
  private readonly max: number

  constructor(max = 64) {
    this.max = max
  }

  get(id: string | null): string | null {
    return id === null ? null : (this.images.get(id) ?? null)
  }

  put(id: string, dataUrl: string): void {
    this.images.delete(id)
    this.images.set(id, dataUrl)
    this.requested.delete(id)
    while (this.images.size > this.max) {
      const oldest = this.images.keys().next().value
      if (oldest === undefined) break
      this.images.delete(oldest)
    }
  }

  /** Store any images in a media.state and return the ids that still need fetching. */
  absorb(state: AgentPayload<'media.state'>): string[] {
    const missing: string[] = []
    for (const s of state.sessions) {
      if (s.artworkId === null) continue
      if (s.artwork !== null) this.put(s.artworkId, s.artwork)
      else if (!this.images.has(s.artworkId) && !this.requested.has(s.artworkId)) {
        this.requested.add(s.artworkId)
        missing.push(s.artworkId)
      }
    }
    return missing
  }

  /** A media.artwork reply arrived (null when the agent no longer has that image). */
  resolve(id: string, dataUrl: string | null): void {
    if (dataUrl !== null) this.put(id, dataUrl)
    else this.requested.delete(id)
  }

  /** Forget pending requests (after a reconnect they must be asked again). */
  resetRequests(): void {
    this.requested.clear()
  }
}

export function currentSession(view: MediaView): MediaSession | null {
  return view.sessions.find((s) => s.id === view.currentId) ?? view.sessions[0] ?? null
}
