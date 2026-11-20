/**
 * Media controls on the phone's lock screen and notification shade, through the Media Session
 * API. Browsers only show those controls while the page is playing audio, so a silent sound
 * loops while something plays on the laptop. The buttons send the usual media messages.
 */
import type { ClientPayload, ClientType, MediaSession } from './protocol.ts'

export type LockAction = 'play' | 'pause' | 'previoustrack' | 'nexttrack' | 'seekbackward' | 'seekforward' | 'seekto' | 'stop'

export const LOCK_ACTIONS: readonly LockAction[] = [
  'play',
  'pause',
  'previoustrack',
  'nexttrack',
  'seekbackward',
  'seekforward',
  'seekto',
  'stop',
]

const SKIP_SECONDS = 10

export interface Outgoing {
  type: ClientType
  payload: ClientPayload<ClientType>
}

/** What a lock-screen button sends to the laptop, for the session on screen. */
export function lockActionMessage(
  action: LockAction,
  sessionId: string | null,
  details: { seekTime?: number | null } = {},
): Outgoing | null {
  const target = sessionId !== null ? { sessionId } : {}
  switch (action) {
    case 'play':
      return { type: 'media.play', payload: target }
    case 'pause':
    case 'stop':
      return { type: 'media.pause', payload: target }
    case 'previoustrack':
      return { type: 'media.prev', payload: target }
    case 'nexttrack':
      return { type: 'media.next', payload: target }
    case 'seekbackward':
      return { type: 'media.seek', payload: { ...target, by: -SKIP_SECONDS } }
    case 'seekforward':
      return { type: 'media.seek', payload: { ...target, by: SKIP_SECONDS } }
    case 'seekto':
      return typeof details.seekTime === 'number' && Number.isFinite(details.seekTime) && details.seekTime >= 0
        ? { type: 'media.seek', payload: { ...target, to: details.seekTime } }
        : null
  }
}

export interface LockMetadata {
  title: string
  artist: string
  album: string
  artwork: { src: string; sizes: string; type: string }[]
}

/** Lock-screen text and picture for a laptop session. */
export function lockMetadata(session: MediaSession, artwork: string | null): LockMetadata {
  return {
    title: session.title || session.appName,
    artist: session.artist || session.appName,
    album: session.album,
    artwork: artwork !== null ? [{ src: artwork, sizes: '256x256', type: 'image/jpeg' }] : [],
  }
}

/** One second of silence as a tiny WAV (8 kHz, 8-bit mono), made here, not downloaded. */
export function silentWavDataUrl(): string {
  const rate = 8000
  const samples = rate
  const bytes = new Uint8Array(44 + samples)
  const view = new DataView(bytes.buffer)
  const text = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i += 1) view.setUint8(offset + i, s.charCodeAt(i))
  }
  text(0, 'RIFF')
  view.setUint32(4, 36 + samples, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, rate, true)
  view.setUint32(28, rate, true) // byte rate
  view.setUint16(32, 1, true) // block align
  view.setUint16(34, 8, true) // bits per sample
  text(36, 'data')
  view.setUint32(40, samples, true)
  bytes.fill(128, 44) // 8-bit silence is the midpoint
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return `data:audio/wav;base64,${btoa(binary)}`
}
