/**
 * Always-on store for media.state, artwork and volume.state, so the state the agent
 * pushes right after connecting is never missed by a screen that mounts later.
 */
import { ArtworkCache, type MediaView } from './media.ts'
import type { AgentPayload } from './protocol.ts'
import type { RemoteClient } from './ws.ts'

export interface MediaSnapshot {
  media: MediaView | null
  volume: AgentPayload<'volume.state'> | null
  /** Bumps whenever an artwork image arrives, so views re-read the cache. */
  artworkVersion: number
}

export class MediaStore {
  readonly artwork = new ArtworkCache()
  private snapshot: MediaSnapshot = { media: null, volume: null, artworkVersion: 0 }
  private readonly listeners = new Set<() => void>()

  constructor(private readonly client: RemoteClient) {
    client.on('auth.ok', () => {
      // A new connection: the agent will resend images, and pending requests are void.
      this.artwork.resetRequests()
    })
    client.on('media.state', (state) => {
      for (const id of this.artwork.absorb(state)) client.send('media.artwork', { artworkId: id })
      this.update({
        media: { sessions: state.sessions, currentId: state.currentId },
        artworkVersion: this.snapshot.artworkVersion + 1,
      })
    })
    client.on('media.artwork', (p) => {
      this.artwork.resolve(p.artworkId, p.artwork)
      this.update({ artworkVersion: this.snapshot.artworkVersion + 1 })
    })
    client.on('volume.state', (volume) => {
      this.update({ volume })
    })
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  readonly getSnapshot = (): MediaSnapshot => this.snapshot

  /** Optimistic local volume while the slider moves; the next volume.state reconciles it. */
  setVolumeLocally(level: number): void {
    if (this.snapshot.volume !== null) this.update({ volume: { ...this.snapshot.volume, level } })
    this.client.send('volume.set', { level })
  }

  private update(patch: Partial<MediaSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch }
    for (const listener of this.listeners) listener()
  }
}
